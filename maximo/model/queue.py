import json
from copy import deepcopy
from uuid import uuid4

from maximo.config.settings import CACHE_DIR, CACHE_QUEUE_FILE


def _ensure_queue_file() -> None:
    # Fresh installs do not have a queue file yet.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not CACHE_QUEUE_FILE.exists():
        CACHE_QUEUE_FILE.write_text("[]\n", encoding="utf-8")


def load_queue() -> list[dict]:
    _ensure_queue_file()

    try:
        queue = json.loads(CACHE_QUEUE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ungueltige queue.json: {exc}") from exc

    if not isinstance(queue, list):
        raise RuntimeError("queue.json muss ein JSON-Array enthalten")

    return queue


def save_queue(queue: list[dict]) -> None:
    _ensure_queue_file()
    CACHE_QUEUE_FILE.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def add_to_queue(entry: dict) -> dict:
    # Keep the caller's dict untouched before queue metadata is added.
    stored_entry = deepcopy(entry)
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
