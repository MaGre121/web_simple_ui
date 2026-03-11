import logging

from maximo.config import settings

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
            # Empty values become input fields in the web UI.
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
        "siteid": settings.DEFAULT_SITEID,
        "orgid": orgid,
        "classstructureid": classstructureid,
        "fixed_specs": fixed_specs,
        "user_specs": user_specs,
        "user_fields": ["serialnum", "location"],
    }


def fetch_templates(server: str, session) -> list[dict]:
    from maximo.oslc.fetch import fetch_all_oslc

    logger.info("Fetching master items...")
    items = fetch_all_oslc(
        server,
        session,
        settings.OSLC_MXITEM_ENDPOINT,
        settings.OSLC_MXITEM_PARAMS,
        max_pages=50,
    )

    templates = [_parse_template(item) for item in items]
    logger.info("Fetched %d templates", len(templates))
    return templates


def save_templates(templates: list[dict]):
    settings.write_json_atomic(settings.CACHE_TEMPLATES_FILE, templates)
    logger.info("Templates saved to %s", settings.CACHE_TEMPLATES_FILE)
