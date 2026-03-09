import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse

from maximo.config import settings
from maximo.model.queue import add_to_queue, load_queue, remove_from_queue, save_queue
from maximo.oslc.post_asset import post_asset
from maximo.oslc.session import create_session, load_environment

logger = logging.getLogger(__name__)

INDEX_FILE = Path(__file__).resolve().parent / "templates" / "index.html"
MAC_SPEC_IDS = {"BAM.MACADRESSE"}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_mac_spec(spec_name: str) -> bool:
    return _clean_text(spec_name).upper() in MAC_SPEC_IDS


def _normalize_mac_address(value: Any, field_label: str) -> str:
    cleaned_value = _clean_text(value)
    if not cleaned_value:
        return ""

    compact_value = re.sub(r"[\s.:-]+", "", cleaned_value)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact_value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ungueltige MAC-Adresse fuer {field_label}: "
                "erwartet NN:NN:NN:NN:NN:NN"
            ),
        )

    compact_value = compact_value.upper()
    return ":".join(
        compact_value[i:i + 2] for i in range(0, len(compact_value), 2)
    )


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
            cleaned_value = _normalize_mac_address(cleaned_value, cleaned_key)

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
    entry = {
        "itemnum": _clean_text(payload.get("itemnum")),
        "description": _clean_text(payload.get("description")),
        "siteid": _clean_text(payload.get("siteid")),
        "orgid": _clean_text(payload.get("orgid")),
        "classstructureid": _clean_text(payload.get("classstructureid")),
        "location": _clean_text(payload.get("location")),
        "serialnum": _clean_text(payload.get("serialnum")),
        "projekt": _clean_text(payload.get("projekt")),
        "users": _normalize_users(payload.get("users")),
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
        session = create_session(token)
        app.state.server = server
        app.state.session = session
        logger.info("Maximo-Session initialisiert fuer %s", server)
    except Exception as exc:
        app.state.startup_error = f"Session-Fehler: {exc}"
        logger.error("Startup fehlgeschlagen: %s", exc)

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def serve_index():
    return FileResponse(INDEX_FILE)


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
    queue = _load_queue_or_http_error()
    updated_queue = add_to_queue(queue, entry)
    save_queue(updated_queue)
    return JSONResponse(updated_queue, status_code=status.HTTP_201_CREATED)


@app.delete("/api/queue/{entry_id}")
def delete_queue_entry(entry_id: str):
    queue = _load_queue_or_http_error()
    removed = remove_from_queue(queue, entry_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Queue-Eintrag nicht gefunden: {entry_id}",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
