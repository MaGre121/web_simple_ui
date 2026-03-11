import logging

from maximo.config import settings

logger = logging.getLogger(__name__)


def _parse_project(item: dict) -> dict:
    return {
        "zustaendigkeit": item.get("spi:zustaendigkeit"),
        "description": item.get("spi:description"),
        "cxprojektid": item.get("spi:cxprojektid"),
        "orgid": item.get("spi:orgid"),
        "projektcode": item.get("spi:projektcode"),
        "vorhabenkennung": item.get("spi:vorhabenkennung"),
    }


def fetch_projects(server: str, session) -> list[dict]:
    from maximo.oslc.fetch import fetch_all_oslc

    logger.info("Fetching projects ...")
    items = fetch_all_oslc(
        server,
        session,
        settings.OSLC_MXPROJECTS_ENDPOINT,
        settings.OSLC_MXPROJECT_PARAMS,
        max_pages=50,
    )

    projects = [_parse_project(item) for item in items]
    logger.info("Fetched %d projects", len(projects))
    return projects


def save_projects(projects: list[dict]):
    settings.write_json_atomic(settings.CACHE_PROJECTS_FILE, projects)
    logger.info("Projects saved to %s", settings.CACHE_PROJECTS_FILE)
