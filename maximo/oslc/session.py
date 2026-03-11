import os

import requests


def load_environment(server: str = "", token: str = ""):
    server = str(server or os.getenv("SERVER") or "").strip()
    token = str(token or os.getenv("MAXIMO_LTPA_TOKEN2") or "").strip()

    if not server or not token:
        raise RuntimeError("SERVER oder MAXIMO_LTPA_TOKEN2 fehlt")

    return server, token


def create_session(ltpa_token: str) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.verify = False
    session.cookies.set("LtpaToken2", ltpa_token)
    return session
