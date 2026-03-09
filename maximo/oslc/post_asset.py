import logging
import re
from typing import Any

import requests

from maximo.config.settings import OSLC_POST_ASSET_ENDPOINT

logger = logging.getLogger(__name__)
MAC_SPEC_IDS = {"BAM.MACADRESSE"}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _pick_text(data: dict, *keys: str) -> str:
    for key in keys:
        value = _clean_text(data.get(key))
        if value:
            return value
    return ""


def _is_mac_spec(attrid: str) -> bool:
    return _clean_text(attrid).upper() in MAC_SPEC_IDS


def _normalize_mac_address(value: str, attrid: str) -> str:
    cleaned_value = _clean_text(value)
    if not cleaned_value:
        return ""

    compact_value = re.sub(r"[\s.:-]+", "", cleaned_value)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact_value):
        raise ValueError(
            f"Ungueltige MAC-Adresse fuer {attrid}: erwartet NN:NN:NN:NN:NN:NN"
        )

    compact_value = compact_value.upper()
    return ":".join(
        compact_value[index:index + 2]
        for index in range(0, len(compact_value), 2)
    )


def _build_assetspec(entry: dict) -> list[dict]:
    merged_specs = {}
    fixed_specs = entry.get("fixed_specs")
    user_specs = entry.get("user_specs")
    if isinstance(fixed_specs, dict):
        merged_specs.update(fixed_specs)
    if isinstance(user_specs, dict):
        merged_specs.update(user_specs)

    assetspec = []
    classstructureid = _pick_text(entry, "classstructureid")
    for attrid, value in merged_specs.items():
        if value in (None, ""):
            continue
        if _is_mac_spec(attrid):
            value = _normalize_mac_address(value, attrid)

        spec_entry = {
            "spi:assetattrid": _clean_text(attrid),
            "spi:alnvalue": value,
        }
        if classstructureid:
            spec_entry["spi:classstructureid"] = classstructureid

        assetspec.append(spec_entry)

    return assetspec


def _build_assetusercust(entry: dict) -> list[dict]:
    users = entry.get("users")
    if not isinstance(users, list):
        users = entry.get("user_secs")
    if not isinstance(users, list):
        return []

    assetusercust = []
    for user in users:
        if not isinstance(user, dict):
            continue

        personid = _pick_text(user, "personid", "spi:personid")
        if not personid:
            continue

        assetusercust.append(
            {
                "spi:personid": personid,
                "spi:isuser": bool(user.get("isuser", False)),
                "spi:iscustodian": bool(user.get("iscustodian", False)),
                "spi:isprimary": bool(user.get("isprimary", False)),
            }
        )

    return assetusercust


def _build_payload(entry: dict) -> dict:
    payload = {}

    required_fields = {
        "spi:itemnum": _pick_text(entry, "itemnum"),
        "spi:siteid": _pick_text(entry, "siteid"),
        "spi:orgid": _pick_text(entry, "orgid"),
        "spi:location": _pick_text(entry, "location"),
        "spi:serialnum": _pick_text(entry, "serialnum"),
    }

    missing_fields = [
        key.removeprefix("spi:")
        for key, value in required_fields.items()
        if not value
    ]
    if missing_fields:
        raise ValueError(
            "Pflichtfelder fehlen fuer Maximo-POST: "
            + ", ".join(missing_fields)
        )

    payload.update(required_fields)

    itemsetid = _pick_text(entry, "itemsetid")
    if itemsetid:
        payload["spi:itemsetid"] = itemsetid

    classstructureid = _pick_text(entry, "classstructureid")
    if classstructureid:
        payload["spi:classstructureid"] = classstructureid

    persongroup = _pick_text(
        entry,
        "group",
        "cxpersongroup",
        "persongroup",
    )
    if persongroup:
        payload["spi:cxpersongroup"] = persongroup

    project = _pick_text(
        entry,
        "cxprojekt",
        "projekt",
        "projektcode",
        "cxprojektid",
    )
    if project:
        payload["spi:cxprojekt"] = project

    assetspec = _build_assetspec(entry)
    if assetspec:
        payload["spi:assetspec"] = assetspec

    assetusercust = _build_assetusercust(entry)
    if assetusercust:
        payload["spi:assetusercust"] = assetusercust

    return payload


def _extract_assetnum_from_json(data: dict) -> str:
    for key in ("spi:assetnum", "assetnum"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _extract_assetnum_from_headers(response: requests.Response) -> str:
    location = response.headers.get("Location") or response.headers.get("location")
    if not location:
        return ""

    assetnum = location.rstrip("/").split("/")[-1]
    return assetnum.split("?", 1)[0]


def _extract_error(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"HTTP {response.status_code}"

    if isinstance(data, dict):
        maximo_error = data.get("Error")
        if isinstance(maximo_error, dict):
            reason = str(maximo_error.get("reasonCode") or "").strip()
            message = str(maximo_error.get("message") or "").strip()
            if reason and message:
                return f"{reason}: {message}"
            if reason or message:
                return reason or message

        oslc_error = data.get("oslc:Error")
        if isinstance(oslc_error, dict):
            status_code = str(oslc_error.get("oslc:statusCode") or "").strip()
            message = str(oslc_error.get("oslc:message") or "").strip()
            if status_code and message:
                return f"{status_code}: {message}"
            if status_code or message:
                return status_code or message

        for key in ("message", "error", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    text = response.text.strip()
    return text[:500] or f"HTTP {response.status_code}"


def post_asset(server: str, session, entry: dict) -> dict:
    try:
        payload = _build_payload(entry)
    except ValueError as exc:
        logger.error(
            "Asset POST abgebrochen fuer item=%s error=%s",
            entry.get("itemnum"),
            exc,
        )
        return {"success": False, "error": str(exc)}

    url = f"{server}{OSLC_POST_ASSET_ENDPOINT}"

    try:
        response = session.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-public-uri": server,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception("Asset POST fehlgeschlagen fuer item=%s", entry.get("itemnum"))
        return {"success": False, "error": str(exc)}

    if not response.ok:
        error = _extract_error(response)
        logger.error(
            "Maximo POST fehlgeschlagen fuer item=%s status=%s error=%s",
            entry.get("itemnum"),
            response.status_code,
            error,
        )
        return {"success": False, "error": error}

    assetnum = ""
    try:
        data = response.json()
    except ValueError:
        data = None

    if isinstance(data, dict):
        assetnum = _extract_assetnum_from_json(data)

    if not assetnum:
        assetnum = _extract_assetnum_from_headers(response)

    return {"success": True, "assetnum": assetnum}
