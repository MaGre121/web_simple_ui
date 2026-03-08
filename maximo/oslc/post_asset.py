import logging
import re

import requests

from maximo.config.settings import OSLC_POST_ASSET_ENDPOINT

logger = logging.getLogger(__name__)
MAC_SPEC_IDS = {"BAM.MACADRESSE"}


def _is_mac_spec(attrid: str) -> bool:
    return str(attrid or "").strip().upper() in MAC_SPEC_IDS


def _normalize_mac_address(value: str, attrid: str) -> str:
    cleaned_value = str(value or "").strip()
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
    merged_specs.update(entry.get("fixed_specs") or {})
    merged_specs.update(entry.get("user_specs") or {})

    assetspec = []
    for attrid, value in merged_specs.items():
        if value in (None, ""):
            continue
        if _is_mac_spec(attrid):
            value = _normalize_mac_address(value, attrid)

        assetspec.append(
            {
                "spi:assetattrid": attrid,
                "spi:alnvalue": value,
            }
        )

    return assetspec


def _build_payload(entry: dict) -> dict:
    payload = {
        "spi:itemnum": entry["itemnum"],
        "spi:siteid": entry["siteid"],
        "spi:orgid": entry["orgid"],
        "spi:location": entry["location"],
        "spi:serialnum": entry["serialnum"],
    }

    if entry.get("classstructureid"):
        payload["spi:classstructureid"] = entry["classstructureid"]

    assetspec = _build_assetspec(entry)
    if assetspec:
        payload["spi:assetspec"] = assetspec

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

    return location.rstrip("/").split("/")[-1]


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
