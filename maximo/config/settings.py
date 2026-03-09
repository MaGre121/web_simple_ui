from pathlib import Path

USE_CACHE = True
USE_ASSET_CACHE = True
GET_ASSETS = False

MAX_PAGES = 1000

BASE_DIR = Path(__file__).resolve().parents[1]

ENV_PATH = BASE_DIR / ".env"
DEFAULT_SITEID = "BWS00001"

CACHE_DIR = BASE_DIR / "cache"
CACHE_RAW_FILE = CACHE_DIR / "locations_raw.json"
CACHE_ASSETS_RAW_FILE = CACHE_DIR / "assets_raw.json"
CACHE_TREE_FILE = CACHE_DIR / "locations_tree.json"
CACHE_ASSETS_TREE_FILE = CACHE_DIR / "assets_tree.json"
CACHE_TEMPLATES_FILE = CACHE_DIR / "templates.json"
CACHE_PROJECTS_FILE = CACHE_DIR / "projects.json"
CACHE_QUEUE_FILE = CACHE_DIR / "queue.json"
CACHE_USERS_FILE = CACHE_DIR / "users.json"
LOC_AREA_DIR = CACHE_DIR / "loc-area"

OSLC_ENDPOINT_LOCATIONS = "/maximo/oslc/os/cxsrklocation"
OSLC_ENDPOINT_ASSETS = "/maximo/oslc/os/bwasset6"
OSLC_ENDPOINT_USERS = "/maximo/oslc/os/cduiuser"
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
    "oslc.pageSize": 200
}
