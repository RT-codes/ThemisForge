"""Failures shared by application operations and their HTTP/MCP adapters."""

from typing import Any

from starlette import status


class ApplicationError(Exception):
    def __init__(self, status_code: int, detail: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(detail)


def invalid(detail: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)
