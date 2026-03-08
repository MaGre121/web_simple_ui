import json
import logging
from maximo.config.settings import OSLC_MXITEM_ENDPOINT, OSLC_MXITEM_PARAMS, DEFAULT_SITEID, CACHE_TEMPLATES_FILE

logger = logging.getLogger(__name__)




def _parse_template(item: dict) -> dict:
    fixed_specs = {}
    user_specs = []
    classstructureid = None

    for spec in item.get("spi:itemspec", []):
        attrid = spec.get("spi:assetattrid")
        if not attrid:
            continue

        classstructureid = classstructureid or spec.get("spi:classstructureid")

        if spec.get("spi:alnvalue"):
            fixed_specs[attrid] = spec["spi:alnvalue"]
        else:
            user_specs.append(attrid)

    orgid = None
    for info in item.get("spi:itemorginfo", []):
        if info.get("spi:orgid"):
            orgid = info["spi:orgid"]
            break

    return {
        "itemnum": item.get("spi:itemnum"),
        "description": item.get("spi:description"),
        "itemsetid": item.get("spi:itemsetid"),
        "siteid": DEFAULT_SITEID,
        "orgid": orgid,
        "classstructureid": classstructureid,
        "fixed_specs": fixed_specs,
        "user_specs": user_specs,
        "user_fields": ["serialnum", "location"]
    }


def fetch_templates(server: str, session) -> list[dict]:
    from maximo.oslc.fetch import fetch_all_oslc

    logger.info("Fetching master items...")
    items = fetch_all_oslc(server, session, OSLC_MXITEM_ENDPOINT, OSLC_MXITEM_PARAMS, max_pages=50)

    templates = [_parse_template(i) for i in items]
    logger.info("Fetched %d templates", len(templates))
    return templates


def save_templates(templates: list[dict]):
    CACHE_TEMPLATES_FILE.write_text(
        json.dumps(templates, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info("Templates saved to %s", CACHE_TEMPLATES_FILE)
