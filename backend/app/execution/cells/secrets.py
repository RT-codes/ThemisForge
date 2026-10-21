import base64
import contextlib
import io
import tarfile

from app.execution.cells.contract import SECRETS_DIR, CellError


def secrets_archive(files: dict[str, str], uid: int = 0, gid: int = 0) -> bytes:
    """A tar stream with the secret files, owner-only (0600), for `tar -x` inside the cell."""
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for path, content in files.items():
            if not path.startswith(SECRETS_DIR + "/") or ".." in path.split("/"):
                raise CellError(f"Secret files must live under {SECRETS_DIR}")
            data = content.encode()
            info = tarfile.TarInfo(path.lstrip("/"))
            info.size, info.mode, info.uid, info.gid = len(data), 0o600, uid, gid
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


WRITEBACK_BEGIN = "@@THEMIS-WRITEBACK-BEGIN "


WRITEBACK_END = "@@THEMIS-WRITEBACK-END@@"


_MARKER = "@@THEMIS-WRITEBACK"


class WritebackFilter:
    """Takes the write-back blocks out of a cell's output so a login never reaches the log.

    A block is `@@THEMIS-WRITEBACK-BEGIN <path>@@`, one line of base64, `@@THEMIS-WRITEBACK-END@@`. Everything else is
    passed through as it arrives; only a partial line that might be the start of a marker is held back.
    """

    def __init__(self, allowed: tuple[str, ...]) -> None:
        self.allowed = allowed
        self.files: dict[str, str] = {}
        self._buf = ""
        self._path: str | None = None  # set while inside a block

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            out.append(self._line(line))
        if (
            self._path is None
            and self._buf
            and not (_MARKER.startswith(self._buf) or self._buf.startswith(_MARKER))
        ):
            out.append(self._buf)
            self._buf = ""
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return "" if self._path is not None or rest.startswith(_MARKER) else rest

    def _line(self, line: str) -> str:
        stripped = line.strip()
        if self._path is not None:
            if stripped == WRITEBACK_END:
                self._path = None
            elif stripped:
                with contextlib.suppress(ValueError):  # a garbled line is dropped, not fatal to the run
                    self.files[self._path] = base64.b64decode(stripped, validate=True).decode()
            return ""
        if stripped.startswith(WRITEBACK_BEGIN) and stripped.endswith("@@"):
            path = stripped[len(WRITEBACK_BEGIN) : -2]
            if path in self.allowed:  # a cell can only write back the files it was asked to
                self._path = path
                return ""
        return line + "\n"
