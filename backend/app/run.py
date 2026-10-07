"""`python -m app.run`: the server, as the installed service starts it (host and port come from the settings)."""

import uvicorn

from .config import settings


def main() -> None:
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
