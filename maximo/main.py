from maximo.config import settings
from maximo.model.location_tree import build_flat_structure, build_tree
from maximo.oslc.fetch import fetch_all_oslc
from maximo.oslc.fetch_projects import fetch_projects, save_projects
from maximo.oslc.fetch_templates import fetch_templates, save_templates
from maximo.oslc.fetch_users import fetch_users, save_users
from maximo.oslc.session import create_session, load_environment


def _fetch_live(server: str, session, endpoint: str, params: dict, label: str) -> list[dict]:
    items = fetch_all_oslc(server, session, endpoint, params, settings.MAX_PAGES)
    print(f"Gesamt geladene {label}: {len(items)}")
    return items


def refresh_master_data(
    server: str,
    session,
    *,
    get_assets: bool | None = None,
) -> dict[str, int]:
    settings.ensure_runtime_dirs()
    include_assets = settings.GET_ASSETS if get_assets is None else get_assets

    locations = _fetch_live(
        server,
        session,
        settings.OSLC_ENDPOINT_LOCATIONS,
        settings.OSLC_PARAMS_LOCATIONS,
        "locations",
    )

    assets: list[dict] = []
    if include_assets:
        assets = _fetch_live(
            server,
            session,
            settings.OSLC_ENDPOINT_ASSETS,
            settings.OSLC_PARAMS_ASSETS,
            "assets",
        )

    users = fetch_users(server, session)
    projects = fetch_projects(server, session)
    templates = fetch_templates(server, session)
    location_tree = build_tree(build_flat_structure(locations))

    settings.write_json_atomic(settings.CACHE_RAW_FILE, locations)
    settings.write_json_atomic(settings.CACHE_TREE_FILE, location_tree)
    if include_assets:
        settings.write_json_atomic(settings.CACHE_ASSETS_RAW_FILE, assets)

    save_users(users)
    save_projects(projects)
    save_templates(templates)

    return {
        "locations": len(locations),
        "assets": len(assets),
        "users": len(users),
        "projects": len(projects),
        "templates": len(templates),
    }


def format_refresh_summary(summary: dict[str, int]) -> str:
    parts = [
        f"Locations {summary['locations']}",
        f"Templates {summary['templates']}",
        f"Projects {summary['projects']}",
        f"Users {summary['users']}",
    ]
    if summary.get("assets"):
        parts.append(f"Assets {summary['assets']}")
    return ", ".join(parts)


def main() -> None:
    server, token = load_environment()
    session = create_session(token)
    summary = refresh_master_data(server, session)
    print(f"Refresh abgeschlossen: {format_refresh_summary(summary)}")


if __name__ == "__main__":
    main()
