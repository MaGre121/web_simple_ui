import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

USE_CACHE = True
USE_ASSET_CACHE = True
GET_ASSETS = False

MAX_PAGES = 1000

BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BASE_DIR.parent
APP_NAME = "MaximoAssetScanUI"
DEFAULT_SITEID = "BWS00001"

def _resolve_resource_base_dir() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", "")
    if bundled_root:
        return Path(bundled_root)
    return PROJECT_ROOT


def _resolve_app_data_dir() -> Path:
    override = str(os.getenv("MAXIMO_APP_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        local_appdata = str(os.getenv("LOCALAPPDATA") or "").strip()
        if local_appdata:
            return Path(local_appdata) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME

    xdg_state_home = str(os.getenv("XDG_STATE_HOME") or "").strip()
    if xdg_state_home:
        return Path(xdg_state_home) / APP_NAME

    xdg_data_home = str(os.getenv("XDG_DATA_HOME") or "").strip()
    if xdg_data_home:
        return Path(xdg_data_home) / APP_NAME

    return Path.home() / ".local" / "share" / APP_NAME


RESOURCE_BASE_DIR = _resolve_resource_base_dir()
WEB_INDEX_FILE = RESOURCE_BASE_DIR / "maximo" / "web" / "templates" / "index.html"
APP_DATA_DIR = _resolve_app_data_dir()
CACHE_DIR = APP_DATA_DIR / "cache"
CACHE_RAW_FILE = CACHE_DIR / "locations_raw.json"
CACHE_ASSETS_RAW_FILE = CACHE_DIR / "assets_raw.json"
CACHE_TREE_FILE = CACHE_DIR / "locations_tree.json"
CACHE_ASSETS_TREE_FILE = CACHE_DIR / "assets_tree.json"
CACHE_TEMPLATES_FILE = CACHE_DIR / "templates.json"
CACHE_PROJECTS_FILE = CACHE_DIR / "projects.json"
CACHE_QUEUE_FILE = CACHE_DIR / "queue.json"
CACHE_USERS_FILE = CACHE_DIR / "users.json"
LOC_AREA_DIR = CACHE_DIR / "loc-area"
LOG_DIR = APP_DATA_DIR / "logs"
RUNTIME_CONFIG_FILE = APP_DATA_DIR / "config.json"

LEGACY_CACHE_DIR = BASE_DIR / "cache"
LEGACY_LOC_AREA_DIR = LEGACY_CACHE_DIR / "loc-area"

_RUNTIME_PATHS_READY = False


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _copy_if_missing(source: Path, target: Path) -> None:
    if target.exists() or not source.exists():
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
        return

    shutil.copy2(source, target)


def _migrate_legacy_cache_if_needed() -> None:
    if not LEGACY_CACHE_DIR.exists() or _same_path(LEGACY_CACHE_DIR, CACHE_DIR):
        return

    file_map = {
        LEGACY_CACHE_DIR / "locations_raw.json": CACHE_RAW_FILE,
        LEGACY_CACHE_DIR / "assets_raw.json": CACHE_ASSETS_RAW_FILE,
        LEGACY_CACHE_DIR / "locations_tree.json": CACHE_TREE_FILE,
        LEGACY_CACHE_DIR / "assets_tree.json": CACHE_ASSETS_TREE_FILE,
        LEGACY_CACHE_DIR / "templates.json": CACHE_TEMPLATES_FILE,
        LEGACY_CACHE_DIR / "projects.json": CACHE_PROJECTS_FILE,
        LEGACY_CACHE_DIR / "queue.json": CACHE_QUEUE_FILE,
        LEGACY_CACHE_DIR / "users.json": CACHE_USERS_FILE,
    }

    for source, target in file_map.items():
        _copy_if_missing(source, target)

    _copy_if_missing(LEGACY_LOC_AREA_DIR, LOC_AREA_DIR)


def ensure_runtime_dirs() -> None:
    global _RUNTIME_PATHS_READY

    if _RUNTIME_PATHS_READY:
        return

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LOC_AREA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_cache_if_needed()
    _RUNTIME_PATHS_READY = True


def write_text_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    ensure_runtime_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(content, encoding=encoding)
    temp_path.replace(path)


def write_json_atomic(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    write_text_atomic(
        path,
        json.dumps(data, indent=indent, ensure_ascii=ensure_ascii) + "\n",
    )


def load_runtime_config() -> dict[str, Any]:
    ensure_runtime_dirs()
    if not RUNTIME_CONFIG_FILE.exists():
        return {}

    try:
        data = json.loads(RUNTIME_CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def save_runtime_config(config: dict[str, Any]) -> None:
    write_json_atomic(RUNTIME_CONFIG_FILE, config)


def load_persisted_server() -> str:
    return str(load_runtime_config().get("server") or "").strip()


def persist_server(server: str) -> str:
    cleaned_server = str(server or "").strip()
    config = load_runtime_config()

    if cleaned_server:
        config["server"] = cleaned_server
    else:
        config.pop("server", None)

    save_runtime_config(config)
    return cleaned_server

OSLC_ENDPOINT_LOCATIONS = "/maximo/oslc/os/cxsrklocation"
OSLC_ENDPOINT_ASSETS = "/maximo/oslc/os/bwasset6"
OSLC_ENDPOINT_USERS = "/maximo/oslc/os/mxapiperuser"
OSLC_MXITEM_ENDPOINT = "/maximo/oslc/os/mxitem"
OSLC_MXPROJECTS_ENDPOINT = "/maximo/oslc/os/cxprojekt"

OSLC_POST_ASSET_ENDPOINT = OSLC_ENDPOINT_ASSETS

OSLC_PARAMS_LOCATIONS = {
    "oslc.where": 'type="IN BETRIEB"',
    "oslc.select": "location,description,siteid,lochierarchy.parent",
    "oslc.pageSize": 200
}

OSLC_PARAMS_ASSETS = {
    "oslc.where":'status="IN BETRIEB"',
    "oslc.select": "location,serialnum,itemnum,assetnum,description",
    "oslc.pageSize": 500
}

OSLC_MXITEM_PARAMS = {
    "oslc.where": 'spi:itemsetid="ITARTIKL"',
    "oslc.select": "itemnum,itemsetid,description,itemorginfo,itemspec",
    "oslc.pageSize": 200
}
OSLC_MXPROJECT_PARAMS = {
    "oslc.where": 'spi:orgid="BTRBZ"',
    "oslc.select": "zustaendigkeit,description,cxprojektid,projektcode,vorhabenkennung",
    "oslc.pageSize": 200
}
OSLC_USERS_PARAMS = {
    "oslc.where": 'spi:status="AKTIV"',
    "oslc.select": "personid",
    "oslc.pageSize": 10000
}
