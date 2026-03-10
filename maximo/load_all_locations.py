import json

from maximo.config import settings
from maximo.export.firmengelaende import export_firmengelaende
from maximo.model.location_tree import build_flat_structure, build_tree
from maximo.oslc.fetch import fetch_all_oslc
from maximo.oslc.session import create_session, load_environment


def load_or_fetch_locations(server: str, session) -> list[dict]:
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOC_AREA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.USE_CACHE and settings.CACHE_RAW_FILE.exists():
        return json.loads(settings.CACHE_RAW_FILE.read_text(encoding="utf-8"))

    locations = fetch_all_oslc(
        server,
        session,
        settings.OSLC_ENDPOINT_LOCATIONS,
        settings.OSLC_PARAMS_LOCATIONS,
        settings.MAX_PAGES,
    )
    settings.CACHE_RAW_FILE.write_text(
        json.dumps(locations, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return locations


def main() -> None:
    server, token = load_environment()
    session = create_session(token)

    # This script only refreshes the location cache/tree.
    locations = load_or_fetch_locations(server, session)
    flat = build_flat_structure(locations)
    tree = build_tree(flat)

    print(f"Flat Locations: {len(flat)}")
    print(f"Root Locations: {len(tree)}")

    settings.CACHE_TREE_FILE.write_text(
        json.dumps(tree, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    export_firmengelaende(tree, 2, settings.LOC_AREA_DIR)


if __name__ == "__main__":
    main()
