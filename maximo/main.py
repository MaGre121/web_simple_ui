import json

from maximo.config import settings
from maximo.oslc.fetch import fetch_all_oslc
from maximo.oslc.fetch_projects import fetch_projects, save_projects
from maximo.oslc.fetch_templates import fetch_templates, save_templates
from maximo.oslc.fetch_users import fetch_users, save_users
from maximo.oslc.session import create_session, load_environment


def _fetch_or_load(
    server: str,
    session,
    endpoint: str,
    params: dict,
    cache_file,
    label: str,
    use_cache: bool,
) -> list[dict]:
    if use_cache and cache_file.exists():
        items = json.loads(cache_file.read_text(encoding="utf-8"))
        print(f"Gesamt geladene {label}: {len(items)} (Cache)")
        return items

    items = fetch_all_oslc(server, session, endpoint, params, settings.MAX_PAGES)
    print(f"Gesamt geladene {label}: {len(items)}")
    cache_file.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return items


def main() -> None:
    server, token = load_environment()
    session = create_session(token)

    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOC_AREA_DIR.mkdir(parents=True, exist_ok=True)

    _fetch_or_load(
        server,
        session,
        settings.OSLC_ENDPOINT_LOCATIONS,
        settings.OSLC_PARAMS_LOCATIONS,
        settings.CACHE_RAW_FILE,
        "locations",
        settings.USE_CACHE,
    )

    # Asset export is optional and can stay disabled for the web UI workflow.
    if settings.GET_ASSETS:
        _fetch_or_load(
            server,
            session,
            settings.OSLC_ENDPOINT_ASSETS,
            settings.OSLC_PARAMS_ASSETS,
            settings.CACHE_ASSETS_RAW_FILE,
            "assets",
            settings.USE_ASSET_CACHE,
        )

    save_users(fetch_users(server, session))
    save_projects(fetch_projects(server, session))
    save_templates(fetch_templates(server, session))


if __name__ == "__main__":
    main()
