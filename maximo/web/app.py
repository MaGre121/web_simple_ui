import json
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse

from maximo.config import settings
from maximo.model.queue import add_to_queue, load_queue, remove_from_queue, save_queue
from maximo.normalization import (
    clean_text as _clean_text,
    is_mac_spec as _is_mac_spec,
    normalize_mac_address,
    pick_text as _pick_text,
)
from maximo.oslc.post_asset import post_asset
from maximo.oslc.session import (
    create_session,
    load_environment,
    read_environment,
    save_environment,
)

logger = logging.getLogger(__name__)

INDEX_FILE = Path(__file__).resolve().parent / "templates" / "index.html"


def _set_session_state(app: FastAPI, server: str, token: str) -> None:
    cleaned_server = _clean_text(server)
    cleaned_token = _clean_text(token)

    if not cleaned_server or not cleaned_token:
        app.state.server = None
        app.state.session = None
        app.state.startup_error = "Session-Fehler: SERVER oder MAXIMO_LTPA_TOKEN2 fehlt"
        return

    app.state.server = cleaned_server
    app.state.session = create_session(cleaned_token)
    app.state.startup_error = None
    logger.info("Maximo-Session initialisiert fuer %s", cleaned_server)


def _connection_payload(payload: dict | None = None) -> tuple[str, str]:
    body = payload or {}
    saved_server, saved_token = read_environment()

    server = _clean_text(body.get("server")) or saved_server
    token = _clean_text(
        body.get("ltpa_token2")
        or body.get("LtpaToken2")
        or body.get("MAXIMO_LTPA_TOKEN2")
    ) or saved_token

    if not server or not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SERVER und LtpaToken2 muessen gesetzt sein.",
        )

    return server, token


def _connection_response(app: FastAPI) -> dict[str, Any]:
    server, token = read_environment()
    return {
        "server": server,
        "ltpa_token2": token,
        "session_ready": bool(getattr(app.state, "server", None) and app.state.session),
        "active_server": _clean_text(getattr(app.state, "server", "")),
        "error": _clean_text(getattr(app.state, "startup_error", "")),
    }


def _normalize_specs(specs: Any, label: str) -> dict[str, str]:
    if specs is None:
        return {}
    if not isinstance(specs, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} muss ein JSON-Objekt sein",
        )

    normalized = {}
    for key, value in specs.items():
        cleaned_key = _clean_text(key)
        if not cleaned_key:
            continue

        cleaned_value = _clean_text(value)
        if _is_mac_spec(cleaned_key):
            try:
                cleaned_value = normalize_mac_address(cleaned_value, cleaned_key)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

        normalized[cleaned_key] = cleaned_value

    return normalized


def _normalize_users(users: Any) -> list[dict]:
    if users is None:
        return []
    if not isinstance(users, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="users muss ein JSON-Array sein",
        )

    normalized = []
    for u in users:
        if not isinstance(u, dict):
            continue
        personid = _clean_text(u.get("personid"))
        if not personid:
            continue
        normalized.append({
            "personid": personid,
            "isprimary": bool(u.get("isprimary", False)),
            "isuser": bool(u.get("isuser", False)),
            "iscustodian": bool(u.get("iscustodian", False)),
        })
    return normalized


def _validate_entry(payload: dict) -> dict:
    # Keep the legacy aliases so existing queue entries stay uploadable.
    projekt = _pick_text(payload, "cxprojekt", "projekt", "projektcode", "cxprojektid")
    projektcode = _pick_text(payload, "projektcode", "projekt", "cxprojekt", "cxprojektid")

    entry = {
        "itemnum": _clean_text(payload.get("itemnum")),
        "description": _clean_text(payload.get("description")),
        "siteid": _clean_text(payload.get("siteid")),
        "orgid": _clean_text(payload.get("orgid")),
        "location": _clean_text(payload.get("location")),
        "serialnum": _clean_text(payload.get("serialnum")),
        "projekt": projekt,
        "cxprojekt": projekt,
        "projektcode": projektcode,
        "cxprojektid": _pick_text(payload, "cxprojektid"),
        "cfglibgroup": _pick_text(
            payload,
            "cfglibgroup",
            "group",
            "cxpersongroup",
            "persongroup",
        ),
        "users": _normalize_users(
            payload.get("users")
            if payload.get("users") is not None
            else payload.get("user_secs")
        ),
        "fixed_specs": _normalize_specs(payload.get("fixed_specs"), "fixed_specs"),
        "user_specs": _normalize_specs(payload.get("user_specs"), "user_specs"),
    }

    required_fields = ("itemnum", "siteid", "orgid", "location", "serialnum", "projekt")
    missing_fields = [field for field in required_fields if not entry[field]]
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pflichtfelder fehlen: {', '.join(missing_fields)}",
        )

    missing_user_specs = [
        key for key, value in entry["user_specs"].items() if not _clean_text(value)
    ]
    if missing_user_specs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pflichtwerte fehlen fuer Specs: {', '.join(missing_user_specs)}",
        )

    primary_count = sum(1 for u in entry["users"] if u["isprimary"])
    if primary_count > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur ein User darf isprimary=true haben.",
        )

    return entry


def _load_templates() -> list[dict]:
    if not settings.CACHE_TEMPLATES_FILE.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Template-Datei fehlt: {settings.CACHE_TEMPLATES_FILE}. "
                "Bitte zuerst den Template-Fetch ausfuehren."
            ),
        )

    try:
        templates = json.loads(settings.CACHE_TEMPLATES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"templates.json ist ungueltig: {exc}",
        ) from exc

    if not isinstance(templates, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="templates.json muss ein JSON-Array enthalten",
        )

    return templates


def _load_json_list(path: Path, label: str) -> list[dict]:
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label}-Datei fehlt: {path}",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{label}-Datei ungueltig: {exc}",
        ) from exc

    if not isinstance(data, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{label}-Datei muss ein JSON-Array enthalten",
        )

    return data


def _normalize_location_option(
    location: Any,
    description: Any,
    siteid: Any,
    parent: Any = None,
) -> dict[str, str] | None:
    cleaned_location = _clean_text(location)
    if not cleaned_location:
        return None

    return {
        "location": cleaned_location,
        "description": _clean_text(description),
        "siteid": _clean_text(siteid),
        "parent": _clean_text(parent),
    }


def _collect_locations_from_tree(
    nodes: Any,
    collected: dict[str, dict[str, str]],
):
    if not isinstance(nodes, dict):
        return

    for loc_id, node in nodes.items():
        if not isinstance(node, dict):
            continue

        option = _normalize_location_option(
            location=node.get("location", loc_id),
            description=node.get("description"),
            siteid=node.get("siteid"),
            parent=node.get("parent"),
        )

        if option and option["location"] not in collected:
            collected[option["location"]] = option

        children = node.get("children")
        if isinstance(children, dict):
            _collect_locations_from_tree(children, collected)


def _load_locations() -> list[dict[str, str]]:
    collected: dict[str, dict[str, str]] = {}

    if settings.CACHE_TREE_FILE.exists():
        try:
            tree_data = json.loads(settings.CACHE_TREE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"locations_tree.json ist ungueltig: {exc}",
            ) from exc

        if not isinstance(tree_data, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="locations_tree.json muss ein JSON-Objekt enthalten",
            )

        _collect_locations_from_tree(tree_data, collected)

    if not collected and settings.CACHE_RAW_FILE.exists():
        try:
            raw_data = json.loads(settings.CACHE_RAW_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"locations_raw.json ist ungueltig: {exc}",
            ) from exc

        if not isinstance(raw_data, list):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="locations_raw.json muss ein JSON-Array enthalten",
            )

        for raw_entry in raw_data:
            if not isinstance(raw_entry, dict):
                continue

            lochierarchy = raw_entry.get("lochierarchy") or raw_entry.get("spi:lochierarchy")
            parent = ""
            if isinstance(lochierarchy, dict):
                parent = lochierarchy.get("parent")

            option = _normalize_location_option(
                raw_entry.get("spi:location") or raw_entry.get("location"),
                raw_entry.get("spi:description") or raw_entry.get("description"),
                raw_entry.get("spi:siteid") or raw_entry.get("siteid"),
                parent,
            )
            if option:
                collected[option["location"]] = option

    if not collected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Keine Location-Datei gefunden. Bitte zuerst "
                "`python -m maximo.main` ausfuehren."
            ),
        )

    return sorted(
        collected.values(),
        key=lambda option: (
            option["location"].lower(),
            option["description"].lower(),
        ),
    )


def _load_queue_or_http_error() -> list[dict]:
    try:
        return load_queue()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Queue konnte nicht geladen werden: {exc}",
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.server = None
    app.state.session = None
    app.state.startup_error = None

    try:
        server, token = load_environment()
        _set_session_state(app, server, token)
    except Exception as exc:
        app.state.startup_error = f"Session-Fehler: {exc}"
        logger.error("Startup fehlgeschlagen: %s", exc)

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def serve_index():
    return FileResponse(INDEX_FILE)


@app.get("/api/settings")
def get_settings(request: Request):
    return JSONResponse(_connection_response(request.app))


@app.post("/api/settings")
def save_settings(request: Request, payload: dict = Body(...)):
    server, token = _connection_payload(payload)
    save_environment(server, token)
    _set_session_state(request.app, server, token)
    return JSONResponse(_connection_response(request.app))


@app.get("/api/templates")
def get_templates():
    return JSONResponse(_load_templates())


@app.get("/api/locations")
def get_locations():
    return JSONResponse(_load_locations())


@app.get("/api/users")
def get_users():
    return JSONResponse(_load_json_list(settings.CACHE_USERS_FILE, "Users"))


@app.get("/api/projects")
def get_projects():
    return JSONResponse(_load_json_list(settings.CACHE_PROJECTS_FILE, "Projects"))


@app.get("/api/queue")
def get_queue():
    return JSONResponse(_load_queue_or_http_error())


@app.post("/api/queue")
def add_queue_entry(payload: dict = Body(...)):
    entry = _validate_entry(payload)
    add_to_queue(entry)
    return JSONResponse(_load_queue_or_http_error(), status_code=status.HTTP_201_CREATED)


@app.delete("/api/queue/{entry_id}")
def delete_queue_entry(entry_id: str):
    removed = remove_from_queue(entry_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Queue-Eintrag nicht gefunden: {entry_id}",
        )

    return JSONResponse(_load_queue_or_http_error())


@app.post("/api/upload")
def upload_queue(request: Request):
    if request.app.state.startup_error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=request.app.state.startup_error,
        )

    if not request.app.state.server or request.app.state.session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Maximo Session ist nicht initialisiert",
        )

    queue = _load_queue_or_http_error()
    results = []
    changed = False

    for entry in queue:
        current_status = entry.get("status") or "pending"
        if current_status == "success":
            continue

        # Keep processing later rows even if one upload fails.
        result = post_asset(
            request.app.state.server,
            request.app.state.session,
            entry,
        )

        entry["status"] = "success" if result["success"] else "error"

        if result.get("assetnum"):
            entry["assetnum"] = result["assetnum"]
        else:
            entry.pop("assetnum", None)

        if result.get("error"):
            entry["error"] = result["error"]
        else:
            entry.pop("error", None)

        results.append({"id": entry.get("id"), **result})
        changed = True

    if changed:
        save_queue(queue)

    return JSONResponse({"queue": queue, "results": results})


@app.post("/api/fetch-data")
def fetch_data(request: Request, payload: dict | None = Body(default=None)):
    server, token = _connection_payload(payload)
    save_environment(server, token)
    _set_session_state(request.app, server, token)

    cmd = [sys.executable, "-m", "maximo.main"]
    logger.info("Starte Datenabruf: %s", " ".join(cmd))

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("PYTHONUTF8", "1")
        result = subprocess.run(
            cmd,
            cwd=str(settings.BASE_DIR.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        return JSONResponse(
            {
                "success": False,
                "stdout": _clean_text(exc.stdout or ""),
                "stderr": _clean_text(exc.stderr or ""),
                "detail": "Datenabruf hat das Zeitlimit ueberschritten.",
            },
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    response = {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": _clean_text(result.stdout),
        "stderr": _clean_text(result.stderr),
    }

    if result.returncode != 0:
        return JSONResponse(
            {
                **response,
                "detail": "Datenabruf fehlgeschlagen.",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return JSONResponse(response)
