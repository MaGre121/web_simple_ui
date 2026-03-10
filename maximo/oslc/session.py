import os

import requests
from dotenv import load_dotenv

from maximo.config.settings import ENV_PATH


def load_environment():
    load_dotenv(dotenv_path=ENV_PATH)

    server = os.getenv("SERVER")
    token = os.getenv("MAXIMO_LTPA_TOKEN2")

    if not server or not token:
        raise RuntimeError("SERVER oder MAXIMO_LTPA_TOKEN2 fehlt")

    return server, token


def create_session(ltpa_token: str) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.verify = False
    session.cookies.set("LtpaToken2", ltpa_token)
    return session
