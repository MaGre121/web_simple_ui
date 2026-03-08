import requests
import os
import json
import re
import unicodedata
from dotenv import load_dotenv
from pathlib import Path

# ============================================================
# 🔧 GLOBALE KONFIGURATION (hier ändern)
# ============================================================

USE_CACHE = True

BASE_DIR = Path(__file__).resolve().parent

ENV_PATH = BASE_DIR / ".env"

CACHE_DIR = BASE_DIR / "cache"
CACHE_RAW_FILE = CACHE_DIR / "locations_raw.json"
CACHE_TREE_FILE = CACHE_DIR / "locations_tree.json"
LOC_AREA_DIR = CACHE_DIR / "loc-area"

OSLC_ENDPOINT = "/maximo/oslc/os/cxsrklocation"

OSLC_PARAMS = {
    "oslc.where": 'type="IN BETRIEB"',
    "oslc.select": "location,description,siteid,lochierarchy.parent",
    "oslc.pageSize": 100
}

MAX_PAGES = 1000

# ============================================================
# 🌱 ENV / CONFIG
# ============================================================

def load_environment():
    load_dotenv(dotenv_path=ENV_PATH)

    server = os.getenv("SERVER")
    ltpa_token = os.getenv("MAXIMO_LTPA_TOKEN2")

    if not server or not ltpa_token:
        raise RuntimeError("SERVER oder MAXIMO_LTPA_TOKEN2 fehlt im .env")

    return server, ltpa_token


# ============================================================
# 🔐 SESSION
# ============================================================

def create_session(ltpa_token: str) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.verify = False
    session.cookies.set("LtpaToken2", ltpa_token)
    return session


# ============================================================
# 🌐 OSLC FETCH
# ============================================================

def fetch_locations_from_oslc(server: str, session: requests.Session) -> list:
    print("🌐 Lade Locations aus Maximo OSLC …")

    all_members = []
    url = f"{server}{OSLC_ENDPOINT}"
    page = 0

    while url and page < MAX_PAGES:
        response = session.get(
            url,
            headers={"Accept": "application/json"},
            params=OSLC_PARAMS if page == 0 else None,
            timeout=30
        )

        print(f"➡️ Request Seite {page + 1}: {response.status_code}")

        if "application/json" not in response.headers.get("Content-Type", ""):
            raise RuntimeError("❌ Kein JSON – LTPA Token vermutlich abgelaufen")

        data = response.json()
        members = data.get("rdfs:member", [])

        if not members:
            break

        all_members.extend(members)

        next_page = (
            data.get("oslc:responseInfo", {})
                .get("oslc:nextPage", {})
                .get("rdf:resource")
        )

        url = next_page
        page += 1

    print(f"✅ Gesamt geladene Locations: {len(all_members)}")
    return all_members


# ============================================================
# 💾 CACHE
# ============================================================

def load_or_fetch_locations(server: str, session: requests.Session) -> list:
    CACHE_DIR.mkdir(exist_ok=True)
    LOC_AREA_DIR.mkdir(parents=True, exist_ok=True)

    if USE_CACHE and CACHE_RAW_FILE.exists():
        print("📦 Lade Locations aus Cache …")
        with open(CACHE_RAW_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    locations = fetch_locations_from_oslc(server, session)

    with open(CACHE_RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(locations, f, indent=2, ensure_ascii=False)

    print(f"💾 Cache gespeichert: {CACHE_RAW_FILE}")
    return locations


# ============================================================
# 🌳 TREE BUILDING
# ============================================================

def build_flat_structure(locations: list) -> dict:
    flat = {}

    for loc in locations:
        loc_id = loc.get("spi:location")
        if not loc_id:
            continue

        parent = None
        lochierarchy = loc.get("lochierarchy")
        if isinstance(lochierarchy, dict):
            parent = lochierarchy.get("parent")

        flat[loc_id] = {
            "location": loc_id,
            "description": loc.get("spi:description"),
            "siteid": loc.get("spi:siteid"),
            "parent": parent,
            "children": {}
        }

    return flat


def build_tree(flat: dict) -> dict:
    tree = {}

    for loc_id, node in flat.items():
        parent = node["parent"]

        if parent and parent in flat:
            flat[parent]["children"][loc_id] = node
        else:
            tree[loc_id] = node

    return tree


# ============================================================
# 🏭 EXPORT FIRMENGELÄNDE (Level 2)
# ============================================================

def export_firmengelaende(tree: dict, target_level: int = 2):
    def walk(nodes: dict, level: int):
        for loc_id, node in nodes.items():
            if level == target_level:
                description = node.get("description", "")
                location = node.get("location", loc_id)

                desc_slug = _slugify(description)

                filename = f"{desc_slug}-({location}).json"
                path = LOC_AREA_DIR / filename

                with open(path, "w", encoding="utf-8") as f:
                    json.dump(node, f, indent=2, ensure_ascii=False)

                print(f"🏭 Firmengelände exportiert: {path}")
                continue

            children = node.get("children", {})
            if children:
                walk(children, level + 1)

    walk(tree, 0)

def _slugify(text: str) -> str:
    if not text:
        return "unbekannt"

    # Unicode normalisieren (ä → a, etc.)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")

    return text


# ============================================================
# 🚀 MAIN
# ============================================================

def main():
    server, ltpa_token = load_environment()
    session = create_session(ltpa_token)

    locations = load_or_fetch_locations(server, session)

    flat = build_flat_structure(locations)
    tree = build_tree(flat)

    print(f"✅ Flat Locations: {len(flat)}")
    print(f"✅ Root Locations: {len(tree)}")

    with open(CACHE_TREE_FILE, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)

    export_firmengelaende(tree)


# ============================================================
# 🏁 START
# ============================================================

if __name__ == "__main__":
    main()
