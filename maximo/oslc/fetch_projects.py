import json
import logging
from maximo.config.settings import OSLC_MXPROJECTS_ENDPOINT, OSLC_MXPROJECT_PARAMS, CACHE_PROJECTS_FILE

logger = logging.getLogger(__name__)

def _parse_projects(item: dict) -> dict:
    return {
        "zustaendigkeit": item.get("spi:zustaendigkeit"),
        "description": item.get("spi:description"),
        "cxprojektid": item.get("spi:cxprojektid"),
        "orgid": item.get("spi:orgid"),
        "projektcode": item.get("spi:projektcode"),
        "vorhabenkennung": item.get("spi:vorhabenkennung")
    }

def fetch_projects(server: str, session) -> list[dict]:
    from maximo.oslc.fetch import fetch_all_oslc

    logger.info("Fetching projects ...")
    items = fetch_all_oslc(server, session, OSLC_MXPROJECTS_ENDPOINT, OSLC_MXPROJECT_PARAMS, max_pages=50)

    projects = [_parse_projects(i) for i in items]
    logger.info("Fetched %d projects", len(projects))
    return projects


def save_projects(templates: list[dict]):
    CACHE_PROJECTS_FILE.write_text(
        json.dumps(templates, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info("Templates saved to %s", CACHE_PROJECTS_FILE)