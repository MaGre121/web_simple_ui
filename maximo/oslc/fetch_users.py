import json
import logging

from maximo.config.settings import CACHE_USERS_FILE, OSLC_ENDPOINT_USERS, OSLC_USERS_PARAMS

logger = logging.getLogger(__name__)


def _parse_user(item: dict) -> dict:
    return {
        "personid": item.get("spi:personid"),
    }


def fetch_users(server: str, session) -> list[dict]:
    from maximo.oslc.fetch import fetch_all_oslc

    logger.info("Fetching users ...")
    items = fetch_all_oslc(
        server,
        session,
        OSLC_ENDPOINT_USERS,
        OSLC_USERS_PARAMS,
        max_pages=100,
    )

    users = [_parse_user(item) for item in items]
    logger.info("Fetched %d users", len(users))
    return users


def save_users(users: list[dict]):
    CACHE_USERS_FILE.write_text(
        json.dumps(users, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Users saved to %s", CACHE_USERS_FILE)
