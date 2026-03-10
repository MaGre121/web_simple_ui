import base64
import logging
import re
from typing import Any

import requests

from maximo.config.settings import OSLC_POST_ASSET_ENDPOINT

logger = logging.getLogger(__name__)
MAC_SPEC_IDS = {"BAM.MACADRESSE"}
SKIPPED_ASSETSPEC_IDS = {"BAM.TYPENBEZEICHNUNG"}


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


def _should_skip_assetspec(attrid: str) -> bool:
    return _clean_text(attrid).upper() in SKIPPED_ASSETSPEC_IDS


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
    return ":".join(compact_value[i:i + 2] for i in range(0, 12, 2))


def _build_create_payload(entry: dict) -> dict:
    payload = {}

    for field in ("itemnum", "siteid", "orgid", "location", "serialnum", "itemsetid"):
        value = _pick_text(entry, field)
        if value:
            payload[field] = value

    persongroup = _pick_text(entry, "group")
    if persongroup:
        payload["cxpersongroup"] = persongroup

    projekt = _pick_text(entry, "cxprojekt")
    if projekt:
        payload["cxprojekt"] = projekt

    classstructureid = _pick_text(entry, "classstructureid")
    if classstructureid:
        payload["classstructureid"] = classstructureid

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


def _build_spec_payload(entry: dict) -> list[dict]:
    user_specs = entry.get("user_specs")
    if not isinstance(user_specs, dict):
        return []

    specs = []
    for attrid, value in user_specs.items():
        if _should_skip_assetspec(attrid):
            continue
        if value in (None, ""):
            continue
        if _is_mac_spec(attrid):
            value = _normalize_mac_address(value, attrid)

        row = {
            "assetattrid": _clean_text(attrid),
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
    return f"{server}{OSLC_POST_ASSET_ENDPOINT}/_{b64}-"


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
    entry: dict,
    asset_uri: str = "",
) -> None:
    specs = _build_spec_payload(entry)
    if not specs:
        return

    siteid = _pick_text(entry, "siteid")
    if assetnum and siteid:
        url = _asset_href(server, assetnum, siteid)
    else:
        url = _normalize_resource_uri(server, asset_uri)
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

    if response.status_code != 200:
        raise RuntimeError(
            f"Spec-Update fehlgeschlagen fuer {assetnum}: "
            f"{response.status_code} {response.text[:500]}"
        )


def post_asset(server: str, session, entry: dict) -> dict:
    try:
        payload = _build_create_payload(entry)
    except ValueError as exc:
        logger.error("Asset POST abgebrochen item=%s error=%s", entry.get("itemnum"), exc)
        return {"success": False, "error": str(exc)}

    url = f"{server}{OSLC_POST_ASSET_ENDPOINT}?lean=1"

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

    if not response.ok:
        error = _extract_error(response)
        logger.error("Maximo POST fehlgeschlagen item=%s status=%s error=%s",
                      entry.get("itemnum"), response.status_code, error)
        return {"success": False, "error": error}

    assetnum = _extract_assetnum(response)
    asset_uri = _extract_resource_uri(response)

    if entry.get("user_specs") and (assetnum or asset_uri):
        try:
            _update_specs(
                server,
                session,
                assetnum,
                entry,
                asset_uri=asset_uri,
            )
        except (RuntimeError, ValueError) as exc:
            logger.error("Asset erstellt, Spec-Update fehlgeschlagen item=%s error=%s",
                          entry.get("itemnum"), exc)
            return {"success": False, "error": str(exc), "assetnum": assetnum}

    return {"success": True, "assetnum": assetnum}
