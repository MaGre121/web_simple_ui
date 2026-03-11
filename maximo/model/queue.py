import json
from copy import deepcopy
from uuid import uuid4

from maximo.config.settings import CACHE_QUEUE_FILE, ensure_runtime_dirs, write_json_atomic
from maximo.normalization import clean_text as _clean_text
from maximo.normalization import pick_text as _pick_text


def _ensure_queue_file() -> None:
    # Fresh installs do not have a queue file yet.
    ensure_runtime_dirs()
    if not CACHE_QUEUE_FILE.exists():
        write_json_atomic(CACHE_QUEUE_FILE, [])


def _normalize_queue_entry(entry):
    if not isinstance(entry, dict):
        return entry

    normalized = deepcopy(entry)
    normalized.pop("classstructureid", None)
    normalized["cfglibgroup"] = _pick_text(
        normalized,
        "cfglibgroup",
        "group",
        "cxpersongroup",
        "persongroup",
    )
    normalized.pop("group", None)
    normalized.pop("cxpersongroup", None)
    normalized.pop("persongroup", None)

    user_specs = normalized.get("user_specs")
    if isinstance(user_specs, dict):
        cleaned_user_specs = {}
        for key, value in user_specs.items():
            cleaned_key = _clean_text(key)
            cleaned_value = _clean_text(value)
            if not cleaned_key or not cleaned_value:
                continue
            cleaned_user_specs[cleaned_key] = cleaned_value
        normalized["user_specs"] = cleaned_user_specs

    return normalized


def load_queue() -> list[dict]:
    _ensure_queue_file()

    try:
        queue = json.loads(CACHE_QUEUE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ungueltige queue.json: {exc}") from exc

    if not isinstance(queue, list):
        raise RuntimeError("queue.json muss ein JSON-Array enthalten")

    normalized_queue = [_normalize_queue_entry(entry) for entry in queue]
    if normalized_queue != queue:
        save_queue(normalized_queue)

    return normalized_queue


def save_queue(queue: list[dict]) -> None:
    _ensure_queue_file()
    normalized_queue = [_normalize_queue_entry(entry) for entry in queue]
    write_json_atomic(CACHE_QUEUE_FILE, normalized_queue)


def add_to_queue(entry: dict) -> dict:
    # Keep the caller's dict untouched before queue metadata is added.
    stored_entry = _normalize_queue_entry(entry)
    stored_entry["id"] = str(uuid4())
    stored_entry["status"] = "pending"

    queue = load_queue()
    queue.append(stored_entry)
    save_queue(queue)

    return stored_entry


def remove_from_queue(entry_id: str) -> bool:
    queue = load_queue()
    filtered_queue = [entry for entry in queue if entry.get("id") != entry_id]

    if len(filtered_queue) == len(queue):
        return False

    save_queue(filtered_queue)
    return True
