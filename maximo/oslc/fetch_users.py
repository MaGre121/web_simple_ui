import logging

from maximo.config import settings

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
        settings.OSLC_ENDPOINT_USERS,
        settings.OSLC_USERS_PARAMS,
        max_pages=100,
    )

    users = [_parse_user(item) for item in items]
    logger.info("Fetched %d users", len(users))
    return users


def save_users(users: list[dict]):
    settings.write_json_atomic(settings.CACHE_USERS_FILE, users)
    logger.info("Users saved to %s", settings.CACHE_USERS_FILE)
