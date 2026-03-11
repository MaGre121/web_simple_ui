import base64
import logging

import requests

from maximo.config.settings import OSLC_POST_ASSET_ENDPOINT
from maximo.normalization import (
    clean_text as _clean_text,
    is_mac_spec as _is_mac_spec,
    normalize_mac_address as _normalize_mac_address,
    pick_text as _pick_text,
)

logger = logging.getLogger(__name__)
SKIPPED_ASSETSPEC_IDS = {"BAM.TYPENBEZEICHNUNG"}


def _should_skip_assetspec(attrid: str) -> bool:
    return _clean_text(attrid).upper() in SKIPPED_ASSETSPEC_IDS


def _trim_text(value: str, limit: int = 1000) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _build_create_payload(entry: dict) -> dict:
    payload = {}

    for field in ("itemnum", "siteid", "orgid", "location", "serialnum", "itemsetid"):
        value = _pick_text(entry, field)
        if value:
            payload[field] = value

    persongroup = _pick_text(entry, "group", "cxpersongroup", "persongroup")
    if persongroup:
        payload["cxpersongroup"] = persongroup

    projekt = _pick_text(entry, "cxprojekt", "projekt", "projektcode", "cxprojektid")
    if projekt:
        payload["cxprojekt"] = projekt

    users = entry.get("users")
    if isinstance(users, list) and users:
        payload["assetusercust"] = [
            {
                "personid": _clean_text(u.get("personid")),
                "isuser": bool(u.get("isuser")),
                "iscustodian": bool(u.get("iscustodian")),
                "isprimary": bool(u.get("isprimary")),
            }
            for u in users
            if _clean_text(u.get("personid"))
        ]

    return payload


def _collect_specs(entry: dict) -> dict[str, str]:
    collected: dict[str, str] = {}

    for key in ("fixed_specs", "user_specs"):
        specs = entry.get(key)
        if not isinstance(specs, dict):
            continue

        for attrid, value in specs.items():
            cleaned_attrid = _clean_text(attrid)
            cleaned_value = _clean_text(value)

            if not cleaned_attrid or not cleaned_value:
                continue
            if _should_skip_assetspec(cleaned_attrid):
                continue
            if _is_mac_spec(cleaned_attrid):
                cleaned_value = _normalize_mac_address(cleaned_value, cleaned_attrid)

            collected[cleaned_attrid] = cleaned_value

    return collected


def _build_spec_payload(entry: dict) -> list[dict]:
    specs = []
    for attrid, value in _collect_specs(entry).items():
        row = {
            "assetattrid": attrid,
            "alnvalue": value,
        }
        specs.append(row)

    return specs


def _extract_resource_uri(response: requests.Response) -> str:
    return _clean_text(
        response.headers.get("Location") or response.headers.get("location")
    )


def _normalize_resource_uri(server: str, resource_uri: str) -> str:
    if not resource_uri:
        return ""
    if resource_uri.startswith("http://") or resource_uri.startswith("https://"):
        return resource_uri
    if resource_uri.startswith("/"):
        return f"{server}{resource_uri}"
    return f"{server}/{resource_uri}"


def _asset_href(server: str, assetnum: str, siteid: str) -> str:
    raw = f"{assetnum}/{siteid}"
    b64 = base64.b64encode(raw.encode()).decode().rstrip("=")
    b64 = b64.replace("+", "-").replace("/", "_")
    return f"{server.rstrip('/')}/{OSLC_POST_ASSET_ENDPOINT}/_{b64}-"


def _decode_asset_href(resource_uri: str) -> tuple[str, str]:
    segment = _clean_text(resource_uri).rstrip("/").split("/")[-1]
    if not (segment.startswith("_") and segment.endswith("-")):
        return "", ""

    encoded = segment[1:-1].replace("-", "+").replace("_", "/")
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.b64decode(encoded + padding).decode()
    except Exception:
        return "", ""

    assetnum, _, siteid = raw.partition("/")
    return _clean_text(assetnum), _clean_text(siteid)


def _extract_assetnum(response: requests.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            return _pick_text(data, "assetnum")
    except ValueError:
        pass

    assetnum, _ = _decode_asset_href(_extract_resource_uri(response))
    if assetnum:
        return assetnum

    return _extract_resource_uri(response).rstrip("/").split("/")[-1].split("?")[0]


def _extract_error(response: requests.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            msg = data.get("Error", {}).get("message", "")
            if msg:
                return msg
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


def _update_specs(
    server: str,
    session,
    assetnum: str,
    siteid: str,
    specs: list[dict],
    asset_uri: str = "",
) -> None:
    if not specs:
        return

    url = _normalize_resource_uri(server, asset_uri)
    if not url and assetnum and siteid:
        url = _asset_href(server, assetnum, siteid)
    if not url:
        raise RuntimeError("Asset-URL fuer Spec-Update konnte nicht bestimmt werden")

    payload = {
        "spi:assetspec": [
            {
                "spi:assetattrid": spec["assetattrid"],
                "spi:linearassetspecid": 0,
                "spi:alnvalue": spec["alnvalue"],
            }
            for spec in specs
        ]
    }

    logger.debug(
        "Spec-Update request asset=%s site=%s url=%s payload=%s",
        assetnum,
        siteid,
        url,
        payload,
    )

    response = session.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-method-override": "PATCH",
            "PATCHTYPE": "MERGE",
            "properties": "assetspec",
            "x-public-uri": server,
        },
        timeout=30,
    )

    logger.debug(
        "Spec-Update response asset=%s status=%s headers=%s body=%s",
        assetnum,
        response.status_code,
        dict(response.headers),
        _trim_text(response.text),
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Spec-Update fehlgeschlagen fuer {assetnum}: "
            f"{response.status_code} {response.text[:500]}"
        )


def post_asset(server: str, session, entry: dict) -> dict:
    try:
        payload = _build_create_payload(entry)
    except ValueError as exc:
        logger.error(
            "Asset POST abgebrochen item=%s error=%s",
            entry.get("itemnum"),
            exc,
        )
        return {"success": False, "error": str(exc)}

    url = f"{server}{OSLC_POST_ASSET_ENDPOINT}?lean=1"

    logger.debug(
        "Asset create request item=%s url=%s payload=%s",
        entry.get("itemnum"),
        url,
        payload,
    )

    try:
        response = session.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "properties": "assetnum",
                "x-public-uri": server,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception("Asset POST fehlgeschlagen item=%s", entry.get("itemnum"))
        return {"success": False, "error": str(exc)}

    logger.debug(
        "Asset create response item=%s status=%s headers=%s body=%s",
        entry.get("itemnum"),
        response.status_code,
        dict(response.headers),
        _trim_text(response.text),
    )

    if not response.ok:
        error = _extract_error(response)
        logger.error(
            "Maximo POST fehlgeschlagen item=%s status=%s error=%s",
            entry.get("itemnum"),
            response.status_code,
            error,
        )
        return {"success": False, "error": error}

    assetnum = _extract_assetnum(response)
    asset_uri = _extract_resource_uri(response)
    specs = _build_spec_payload(entry)

    # Create the asset first, then merge specs so we do not replace existing rows.
    if specs and (assetnum or asset_uri):
        try:
            _update_specs(
                server,
                session,
                assetnum,
                _pick_text(entry, "siteid"),
                specs,
                asset_uri=asset_uri,
            )
        except (RuntimeError, ValueError) as exc:
            logger.error(
                "Asset erstellt, Spec-Update fehlgeschlagen item=%s error=%s",
                entry.get("itemnum"),
                exc,
            )
            return {"success": False, "error": str(exc), "assetnum": assetnum}

    return {"success": True, "assetnum": assetnum}
