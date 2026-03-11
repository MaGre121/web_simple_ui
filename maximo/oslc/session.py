import requests

from maximo.config.settings import ENV_PATH


def _parse_env_value(raw: str) -> str:
    value = str(raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def _format_env_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(ch.isspace() for ch in text) or "#" in text or '"' in text:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _read_env_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}

    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = _parse_env_value(raw_value)

    return values


def read_environment() -> tuple[str, str]:
    values = _read_env_map()
    server = str(values.get("SERVER") or "").strip()
    token = str(values.get("MAXIMO_LTPA_TOKEN2") or "").strip()
    return server, token


def load_environment():
    server, token = read_environment()

    if not server or not token:
        raise RuntimeError("SERVER oder MAXIMO_LTPA_TOKEN2 fehlt")

    return server, token


def save_environment(server: str, token: str) -> tuple[str, str]:
    cleaned_server = str(server or "").strip()
    cleaned_token = str(token or "").strip()

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    updates = {
        "SERVER": cleaned_server,
        "MAXIMO_LTPA_TOKEN2": cleaned_token,
    }
    seen_keys: set[str] = set()
    rendered_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered_lines.append(line)
            continue

        key, _ = line.split("=", 1)
        clean_key = key.strip()
        if clean_key in updates:
            if clean_key in seen_keys:
                continue
            rendered_lines.append(f"{clean_key}={_format_env_value(updates[clean_key])}")
            seen_keys.add(clean_key)
            continue

        rendered_lines.append(line)

    for key, value in updates.items():
        if key not in seen_keys:
            rendered_lines.append(f"{key}={_format_env_value(value)}")

    ENV_PATH.write_text("\n".join(rendered_lines).rstrip() + "\n", encoding="utf-8")

    return cleaned_server, cleaned_token


def create_session(ltpa_token: str) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.verify = False
    session.cookies.set("LtpaToken2", ltpa_token)
    return session
