import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    uvicorn.run(
        "maximo.web.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="debug",
    )


if __name__ == "__main__":
    main()
