import logging
import re
from typing import Any

import requests

from maximo.config.settings import OSLC_POST_ASSET_ENDPOINT

logger = logging.getLogger(__name__)
MAC_SPEC_IDS = {"BAM.MACADRESSE"}
SKIPPED_ASSETSPEC_IDS = {"BAM.TYPENBEZEICHNUNG"}
ASSET_READ_SELECT = (
    "assetnum,siteid,"
    "assetspec{assetattrid,alnvalue,classstructureid,"
    "section,linearassetspecid,href,localuri}"
)


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
    return ":".join(
        compact_value[index:index + 2]
        for index in range(0, len(compact_value), 2)
    )


def _build_assetspec(entry: dict) -> list[dict]:
    user_specs = entry.get("user_specs")
    if not isinstance(user_specs, dict):
        return []

    assetspec = []
    classstructureid = _pick_text(entry, "classstructureid")
    for attrid, value in user_specs.items():
        if _should_skip_assetspec(attrid):
            continue
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


def _get_asset_response(server: str, session, asset_uri: str) -> requests.Response:
    url = _normalize_resource_uri(server, asset_uri)
    if not url:
        raise RuntimeError("Kein Asset-URI aus dem Create-Response erhalten")
    return session.get(
        url,
        headers={
            "Accept": "application/json",
            "x-public-uri": server,
        },
        params={
            "lean": 1,
            "_format": "json",
            "oslc.format": "application/json",
            "oslc.select": ASSET_READ_SELECT,
        },
        timeout=30,
    )


def _get_asset_lookup_response(
    server: str,
    session,
    assetnum: str,
    siteid: str,
) -> requests.Response:
    return session.get(
        f"{server}{OSLC_POST_ASSET_ENDPOINT}",
        headers={
            "Accept": "application/json",
            "x-public-uri": server,
        },
        params={
            "lean": 1,
            "_format": "json",
            "oslc.format": "application/json",
            "oslc.where": f'assetnum="{assetnum}" and siteid="{siteid}"',
            "oslc.select": ASSET_READ_SELECT,
            "oslc.pageSize": 1,
        },
        timeout=30,
    )


def _extract_assetnum_from_asset(data: dict) -> str:
    return _pick_text(data, "spi:assetnum", "assetnum")


def _extract_assetspec_rows(asset: dict) -> list[dict]:
    rows = asset.get("spi:assetspec")
    if isinstance(rows, list):
        return rows

    rows = asset.get("assetspec")
    if isinstance(rows, list):
        return rows

    return []


def _extract_asset_from_response(response: requests.Response) -> dict | None:
    if not response.ok:
        return None

    if "application/json" not in response.headers.get("Content-Type", ""):
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if not isinstance(data, dict):
        return None

    members = data.get("rdfs:member")
    if isinstance(members, list):
        for member in members:
            if isinstance(member, dict):
                return member
        return None

    return data


def _describe_response(response: requests.Response) -> str:
    content_type = _clean_text(response.headers.get("Content-Type"))
    text = _clean_text(response.text)[:300]
    if text:
        return (
            f"status={response.status_code} content_type={content_type or '-'} "
            f"body={text}"
        )
    return f"status={response.status_code} content_type={content_type or '-'}"


def _build_assetspec_update_rows(asset: dict, entry: dict) -> list[dict]:
    assetnum = _extract_assetnum_from_asset(asset)
    siteid = _pick_text(asset, "spi:siteid", "siteid") or _pick_text(entry, "siteid")
    existing_rows = {}
    for row in _extract_assetspec_rows(asset):
        if not isinstance(row, dict):
            continue
        attrid = _pick_text(row, "spi:assetattrid", "assetattrid")
        if not attrid:
            continue
        existing_rows[attrid.upper()] = row

    updates = []
    for spec_entry in _build_assetspec(entry):
        attrid = _pick_text(spec_entry, "spi:assetattrid", "assetattrid")
        row = existing_rows.get(attrid.upper())
        if row is None:
            raise ValueError(
                f"Spec nicht gefunden nach Asset-Create: {attrid}"
            )

        update_row = {
            "spi:assetattrid": attrid,
            "spi:alnvalue": spec_entry["spi:alnvalue"],
        }

        href = _pick_text(row, "href", "localuri")
        if href:
            update_row["href"] = href
        else:
            if assetnum:
                update_row["spi:assetnum"] = assetnum
            if siteid:
                update_row["spi:siteid"] = siteid

            section = _pick_text(row, "spi:section", "section")
            if section:
                update_row["spi:section"] = section

            linearassetspecid = _pick_text(
                row,
                "spi:linearassetspecid",
                "linearassetspecid",
            )
            if linearassetspecid:
                update_row["spi:linearassetspecid"] = linearassetspecid

        updates.append(update_row)

    return updates


def _update_asset_specs(
    server: str,
    session,
    asset_uri: str,
    entry: dict,
    assetnum_hint: str = "",
) -> str:
    get_response = _get_asset_response(server, session, asset_uri)
    asset = _extract_asset_from_response(get_response)
    if asset is None:
        assetnum = assetnum_hint or _pick_text(entry, "assetnum")
        siteid = _pick_text(entry, "siteid")
        lookup_response = None
        if assetnum and siteid:
            lookup_response = _get_asset_lookup_response(
                server,
                session,
                assetnum,
                siteid,
            )
            asset = _extract_asset_from_response(lookup_response)

        if asset is None:
            details = [
                "Asset wurde erstellt, aber der Readback fuer das Spec-Update lieferte kein JSON",
                f"Location-GET: {_describe_response(get_response)}",
            ]
            if lookup_response is not None:
                details.append(f"Collection-GET: {_describe_response(lookup_response)}")
            raise RuntimeError(" | ".join(details))

    assetnum = _extract_assetnum_from_asset(asset)
    updates = _build_assetspec_update_rows(asset, entry)
    if not updates:
        return assetnum

    patch_response = session.post(
        _normalize_resource_uri(server, asset_uri),
        json={"spi:assetspec": updates},
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-public-uri": server,
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "properties": "assetnum",
        },
        timeout=30,
    )
    if not patch_response.ok:
        raise RuntimeError(_extract_error(patch_response))

    if not assetnum:
        try:
            patch_data = patch_response.json()
        except ValueError:
            patch_data = None
        if isinstance(patch_data, dict):
            assetnum = _extract_assetnum_from_asset(patch_data)

    return assetnum


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


def _build_create_payload(entry: dict) -> dict:
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

    classstructureid = _pick_text(entry, "classstructureid")
    if classstructureid:
        payload["spi:classstructureid"] = classstructureid

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
        payload = _build_create_payload(entry)
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
                "properties": "assetnum",
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

    asset_uri = _extract_resource_uri(response)
    assetnum = ""
    try:
        data = response.json()
    except ValueError:
        data = None

    if isinstance(data, dict):
        assetnum = _extract_assetnum_from_json(data)

    if entry.get("user_specs"):
        try:
            updated_assetnum = _update_asset_specs(
                server,
                session,
                asset_uri,
                entry,
                assetnum_hint=assetnum,
            )
        except RuntimeError as exc:
            logger.error(
                "Asset erstellt, aber Spec-Update fehlgeschlagen fuer item=%s error=%s",
                entry.get("itemnum"),
                exc,
            )
            if not assetnum:
                assetnum = _extract_assetnum_from_headers(response)
            result = {"success": False, "error": str(exc)}
            if assetnum:
                result["assetnum"] = assetnum
            return result

        if updated_assetnum:
            assetnum = updated_assetnum

    if not assetnum:
        assetnum = _extract_assetnum_from_headers(response)

    return {"success": True, "assetnum": assetnum}
