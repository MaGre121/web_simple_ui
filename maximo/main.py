from maximo.config import settings
from maximo.oslc.assets import fetch_assets_for_location, add_asset
from maximo.oslc.fetch_templates import fetch_templates, save_templates
from maximo.oslc.session import load_environment, create_session
from maximo.oslc.fetch import fetch_all_oslc
from maximo.model.location_tree import build_flat_structure, build_tree, prune_tree
from maximo.model.asset_tree import index_assets_by_location
from maximo.export.firmengelaende import export_firmengelaende
import json

def main():
    server, token = load_environment()
    session = create_session(token)

    settings.CACHE_DIR.mkdir(exist_ok=True)
    settings.LOC_AREA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.USE_CACHE and settings.CACHE_RAW_FILE.exists():
        locations = json.loads(
            settings.CACHE_RAW_FILE.read_text(encoding="utf-8")
        )
        print(f"✅ Gesamt geladene locations: {len(locations)}")
    else:
        # Hole alle Locations
        locations = fetch_all_oslc(
            server,
            session,
            settings.OSLC_ENDPOINT_LOCATIONS,
            settings.OSLC_PARAMS_LOCATIONS,
            settings.MAX_PAGES
        )
        # schreibe locations raw
        settings.CACHE_RAW_FILE.write_text(json.dumps(locations, indent=2))

    if settings.USE_ASSET_CACHE and settings.CACHE_ASSETS_RAW_FILE.exists():
        assets = json.loads(
            settings.CACHE_ASSETS_RAW_FILE.read_text(encoding="utf-8")
        )
        print(f"✅ Gesamt geladene assets: {len(assets)}")
    # hole alle assets
    else:
        if settings.GET_ASSETS:
            assets = fetch_all_oslc(
                server,
                session,
                settings.OSLC_ENDPOINT_ASSETS,
                settings.OSLC_PARAMS_ASSETS,
                settings.MAX_PAGES
            )
            print(f"✅ Gesamt geladene assets: {len(assets)}")
            # schreibe assets raw
            settings.CACHE_ASSETS_RAW_FILE.write_text(json.dumps(assets, indent=2))




    # asset_tree = index_assets_by_location(assets)
    # flat = build_flat_structure(locations, asset_tree)
    # full_tree = build_tree(flat)
    # asset_tree = prune_tree(full_tree)
    #
    # settings.CACHE_ASSETS_TREE_FILE.write_text(json.dumps(asset_tree, indent=2))
    # settings.CACHE_TREE_FILE.write_text(json.dumps(asset_tree, indent=2))
    # export_firmengelaende(asset_tree, 2, settings.LOC_AREA_DIR)
    # add_asset(server, session, "BOR14900","asdf1234", "aa:bb:cc:dd:ee")
    templates = fetch_templates(server, session)
    save_templates(templates)


if __name__ == "__main__":
    main()
