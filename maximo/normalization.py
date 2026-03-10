import re
from typing import Any, Mapping


MAC_SPEC_IDS = {"BAM.MACADRESSE"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def pick_text(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = clean_text(data.get(key))
        if value:
            return value
    return ""


def is_mac_spec(attrid: str) -> bool:
    return clean_text(attrid).upper() in MAC_SPEC_IDS


def normalize_mac_address(value: Any, field_label: str) -> str:
    cleaned_value = clean_text(value)
    if not cleaned_value:
        return ""

    compact_value = re.sub(r"[\s.:-]+", "", cleaned_value)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact_value):
        raise ValueError(
            f"Ungueltige MAC-Adresse fuer {field_label}: erwartet NN:NN:NN:NN:NN:NN"
        )

    compact_value = compact_value.upper()
    return ":".join(
        compact_value[index:index + 2]
        for index in range(0, len(compact_value), 2)
    )
