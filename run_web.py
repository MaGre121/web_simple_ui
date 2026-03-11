import logging

import uvicorn

from maximo.web.app import app


def main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="debug",
    )


if __name__ == "__main__":
    main()
