import json
import logging
from maximo.config.settings import OSLC_ENDPOINT_USERS, OSLC_USERS_PARAMS, CACHE_USERS_FILE

logger = logging.getLogger(__name__)

def _parse_users(item: dict) -> dict:
    return {
        "personid": item.get("spi:personid")
    }

def fetch_users(server: str, session) -> list[dict]:
    from maximo.oslc.fetch import fetch_all_oslc

    logger.info("Fetching projects ...")
    items = fetch_all_oslc(server, session, OSLC_ENDPOINT_USERS, OSLC_USERS_PARAMS, max_pages=50)

    users = [_parse_users(i) for i in items]
    logger.info("Fetched %d projects", len(users))
    return users


def save_users(users: list[dict]):
    CACHE_USERS_FILE.write_text(
        json.dumps(users, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info("Templates saved to %s", CACHE_USERS_FILE)