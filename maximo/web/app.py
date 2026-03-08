import json
import logging
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


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_specs(specs: Any, field_name: str) -> dict[str, str]:
    if specs is None:
        return {}
    if not isinstance(specs, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} muss ein Objekt sein",
        )

    normalized = {}
    for key, value in specs.items():
        cleaned_key = _clean_text(key)
        if not cleaned_key:
            continue
        normalized[cleaned_key] = _clean_text(value)

    return normalized


def _validate_queue_entry(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltiger Queue-Eintrag",
        )

    entry = {
        "itemnum": _clean_text(payload.get("itemnum")),
        "description": _clean_text(payload.get("description")),
        "siteid": _clean_text(payload.get("siteid")),
        "orgid": _clean_text(payload.get("orgid")),
        "classstructureid": _clean_text(payload.get("classstructureid")),
        "location": _clean_text(payload.get("location")),
        "serialnum": _clean_text(payload.get("serialnum")),
        "fixed_specs": _normalize_specs(payload.get("fixed_specs"), "fixed_specs"),
        "user_specs": _normalize_specs(payload.get("user_specs"), "user_specs"),
    }

    required_fields = ("itemnum", "siteid", "orgid", "location", "serialnum")
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


def _load_queue_or_http_error() -> list[dict]:
    try:
        return load_queue()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not settings.CACHE_QUEUE_FILE.exists():
        settings.CACHE_QUEUE_FILE.write_text("[]\n", encoding="utf-8")

    app.state.server = None
    app.state.session = None
    app.state.startup_error = None

    try:
        server, token = load_environment()
        app.state.server = server
        app.state.session = create_session(token)
        logger.info("Maximo Session erfolgreich initialisiert")
    except Exception as exc:  # pragma: no cover - startup protection
        app.state.startup_error = str(exc)
        logger.warning("Maximo Session konnte nicht initialisiert werden: %s", exc)

    yield

    session = getattr(app.state, "session", None)
    if session is not None:
        session.close()


app = FastAPI(title="Maximo Asset Scan UI", lifespan=lifespan)


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(INDEX_FILE)


@app.get("/api/templates")
def get_templates():
    return JSONResponse(_load_templates())


@app.post("/api/queue", status_code=status.HTTP_201_CREATED)
def create_queue_entry(payload: dict[str, Any] = Body(...)):
    entry = _validate_queue_entry(payload)
    try:
        created_entry = add_to_queue(entry)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return JSONResponse(created_entry, status_code=status.HTTP_201_CREATED)


@app.get("/api/queue")
def get_queue():
    return JSONResponse(_load_queue_or_http_error())


@app.delete("/api/queue/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_queue_entry(entry_id: str):
    try:
        removed = remove_from_queue(entry_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

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
        if entry.get("status") != "pending":
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
