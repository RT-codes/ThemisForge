"""Tool servers from the official MCP Registry (registry.modelcontextprotocol.io).

The registry only lists metadata: one server.json per server, saying how to run it (an npm or PyPI package, a container,
a hosted address...). This module turns an entry into what a Themis tool is made of (McpIn), or into the one reason
Themis cannot run it yet, so the app can list everything and grey out what it cannot use.

Nothing in an entry is trusted: anyone can publish one, and a package name or version ends up as an argument of a
command that runs in a cell. So each is checked against the shape a real one has before it is used, and a package that
names some other package registry is refused rather than run under the same name.
"""

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

import yaml
from pydantic import BaseModel, Field

from app.features.tools.keys import ENV_NAME
from app.features.tools.mcp import MAX_REPLY, NAME, McpIn
from app.features.tools.toolcheck import commands_in_image

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
# The tools shown first. A plain file so it can be edited by hand: it is read on every request, no restart needed.
FEATURED_FILE = Path(__file__).with_name("featured_tools.yaml")
CACHE_SECONDS = 300
MAX_CACHED = 200
FETCH_SECONDS = 10

# What cells can start a package with: the programs a registry package maps to. Whether the image has them is
# looked up per image (see available_runners).
RUNNERS = ("npx", "uvx")

REGISTRY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_NPM_NAME = re.compile(r"^(@[A-Za-z0-9][A-Za-z0-9._~-]*/)?[A-Za-z0-9][A-Za-z0-9._~-]*$")
_PYPI_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+!_-]*$")
_TEMPLATE_VARIABLE = re.compile(r"\{([^{}]+)\}")
_BEARER_TEMPLATE = re.compile(r"^Bearer \{[^{}]+\}$")
# The only package registries a package may come from: its entry may name another, which would be a different
# package under the same name.
_DEFAULT_REGISTRIES = {"npm": "https://registry.npmjs.org", "pypi": "https://pypi.org"}

# Why a tool cannot be added, as one bucket each. The text is for people.
REASONS = {
    "container": "It is shipped as a container image, and cells cannot start containers.",
    "dotnet": "It needs the .NET runtime, which cell images do not have.",
    "bundle": "It is a desktop extension bundle (.mcpb), which Themis cannot run.",
    "sse": "It only offers the older SSE connection, which Themis does not support yet.",
    "headers": "It needs custom request headers, which Themis does not support yet.",
    "server_package": "It is a package that starts its own web server, which a cell cannot expose.",
    "runtime": "It asks to be started with a program Themis does not offer.",
    "needs_setup": "It needs setup Themis cannot express yet, such as values built from other values.",
    "empty": "The entry does not say how to connect to it.",
    "other": "Themis cannot run this kind of entry yet.",
}


class ToolInput(BaseModel):
    """Something a person fills in before the tool can be made."""

    id: str
    label: str
    description: str = ""
    required: bool = False
    secret: bool = (
        False  # a stored key is chosen for it (the value is the key's id): a secret is never typed here
    )
    choices: list[str] = Field(default_factory=list)
    default: str = ""


class RegistryTool(BaseModel):
    """One registry entry as the app lists it."""

    name: str  # the registry's name for it, such as io.github.github/github-mcp-server
    title: str
    description: str
    version: str
    repository: str = ""
    source: str = ""  # how it would run: "package" (in the cell) or "remote" (a hosted address)
    runs: str = ""  # what would be started or connected to, shown before it is added
    command: str = ""  # the program a package needs in the image
    supported: bool
    reason: str = ""  # a key of REASONS, or "image_command"
    reason_text: str = ""
    inputs: list[ToolInput] = Field(default_factory=list)
    note: str = ""  # from the featured list
    # What the catalog adds (see app/features/tools/catalog.py); empty for a single entry looked up on its own
    icon: str = ""  # an image address to show, or "" for none
    category: str = ""
    downloads: int | None = (
        None  # npm downloads in the last month, when it is an npm package that has been counted
    )
    updated: str = ""


class MissingInput(ValueError):
    """Required inputs were not given (the message names them)."""


class _Blocked(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


@dataclass
class _Option:
    """One way to run an entry. `build` turns the person's answers into the fields of a tool."""

    source: str
    runs: str
    command: str = ""
    inputs: list[ToolInput] = field(default_factory=list)
    build: Callable[[dict[str, str]], dict[str, Any]] | None = None
    reason: str = ""  # set when it cannot be run

    @property
    def way(self) -> "Way":
        return Way(self.source, self.runs, self.command, self.reason)


class Way(NamedTuple):
    """What is left of an option once its inputs are set aside: enough to say whether, and how, a tool can be run.
    The catalog keeps these for every tool; the full option is only built for the one a person picks."""

    source: str  # "package" | "remote" | ""
    runs: str
    command: str  # the program a package needs in the image
    reason: str  # "" when it can be run


def pick_way(ways: list[Way], available: frozenset[str] | None) -> Way:
    """The first way that can be used here, else the first one (whose reason is then the one shown). `available` is
    the programs the image has (None when that is not known: nothing is held against a tool then)."""
    if not ways:
        return Way("", "", "", "empty")
    for way in ways:
        if not way.reason and (available is None or not way.command or way.command in available):
            return way
    for way in ways:
        if not way.reason:  # runnable, but the image lacks the program: say which
            return Way(way.source, way.runs, way.command, "image_command")
    return ways[0]


# ----- turning an entry into a way to run it -----


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _input(prefix: str, key: str, spec: dict, label: str, *, secret: bool | None = None) -> ToolInput:
    choices = [c for c in spec.get("choices") or [] if isinstance(c, str)]
    return ToolInput(
        id=f"{prefix}:{key}",
        label=label,
        description=_text(spec.get("description"))[:500],
        required=bool(spec.get("isRequired")),
        secret=bool(spec.get("isSecret")) if secret is None else secret,
        choices=choices,
        default=_text(spec.get("default")),
    )


def _flag(argument: dict) -> list[str]:
    """The words of an argument that is always passed as written: `--flag value`, or a bare value."""
    value = _text(argument.get("value"))
    if argument.get("type") == "named":
        name = _text(argument.get("name"))
        if not name:
            raise _Blocked("other")
        return [name, value] if value else [name]
    if not value:
        raise _Blocked("other")
    return [value]


def _runtime_arguments(items: list) -> list[str]:
    """Arguments for the program that starts the package (npx, uvx). Only fixed ones are understood."""
    words: list[str] = []
    for argument in items:
        if not isinstance(argument, dict) or "{" in _text(argument.get("value")) or argument.get("variables"):
            raise _Blocked("needs_setup")
        asks = argument.get("isRequired") or argument.get("valueHint") or argument.get("default")
        if not _text(argument.get("value")) and (argument.get("type") != "named" or asks):
            raise _Blocked("needs_setup")
        words += _flag(argument)
    return words


def _package_arguments(items: list, inputs: list[ToolInput]) -> list[Callable[[dict[str, str]], list[str]]]:
    """Arguments for the package itself: fixed ones are written as they are, the rest are asked for."""
    parts: list[Callable[[dict[str, str]], list[str]]] = []
    for index, argument in enumerate(items):
        if not isinstance(argument, dict):
            raise _Blocked("other")
        value = _text(argument.get("value"))
        if "{" in value or argument.get("variables"):
            raise _Blocked("needs_setup")
        if value:
            fixed = _flag(argument)
            parts.append(lambda _values, fixed=fixed: fixed)
            continue
        if argument.get("isSecret"):  # a key must never be an argument: it would show in the process list
            raise _Blocked("needs_setup")
        label = _text(argument.get("valueHint")) or _text(argument.get("name")) or f"Argument {index + 1}"
        spec = _input("arg", str(index), argument, label)
        inputs.append(spec)
        name = _text(argument.get("name")) if argument.get("type") == "named" else ""

        def ask(values: dict[str, str], spec=spec, name=name) -> list[str]:
            given = values.get(spec.id, "").strip() or spec.default
            if not given:
                return []
            return [name, given] if name else [given]

        parts.append(ask)
    return parts


def npm_identifier(entry: dict) -> str:
    """The npm package an entry would run in a cell ("" when it has none that can be run). Used to count downloads."""
    for package in entry.get("packages") or []:
        if not isinstance(package, dict) or package.get("registryType") != "npm":
            continue
        base = _text(package.get("registryBaseUrl")).rstrip("/")
        identifier = _text(package.get("identifier"))
        if (not base or base == _DEFAULT_REGISTRIES["npm"]) and _NPM_NAME.match(identifier):
            return identifier
    return ""


def _package_option(package: dict, version_of_entry: str) -> _Option:
    kind = package.get("registryType")
    identifier = _text(package.get("identifier"))
    version = _text(package.get("version")) or version_of_entry
    source = f"{kind} package {identifier}" if identifier else f"{kind} package"
    blocked = {"oci": "container", "nuget": "dotnet", "mcpb": "bundle"}
    if kind in blocked:
        return _Option("package", source, reason=blocked[kind])
    if kind not in _DEFAULT_REGISTRIES:
        return _Option("package", source, reason="other")
    if package.get("transport", {}).get("type") != "stdio":
        return _Option("package", source, reason="server_package")
    hint = _text(package.get("runtimeHint"))
    command = {"npm": "npx", "pypi": "uvx"}[kind]
    if hint not in ("", command):
        return _Option("package", source, reason="runtime")
    base = _text(package.get("registryBaseUrl")).rstrip("/")
    name_ok = (_NPM_NAME if kind == "npm" else _PYPI_NAME).match(identifier)
    if (base and base != _DEFAULT_REGISTRIES[kind]) or not name_ok or not _VERSION.match(version):
        return _Option("package", source, reason="other")

    inputs: list[ToolInput] = []
    try:
        runtime = [w for w in _runtime_arguments(package.get("runtimeArguments") or []) if w != "-y"]
        arguments = _package_arguments(package.get("packageArguments") or [], inputs)
        env_fixed: dict[str, str] = {}
        env_asked: list[ToolInput] = []
        for variable in package.get("environmentVariables") or []:
            name = _text(variable.get("name")) if isinstance(variable, dict) else ""
            if not ENV_NAME.match(name):
                raise _Blocked("other")
            value = _text(variable.get("value"))
            if "{" in value or variable.get("variables"):
                raise _Blocked("needs_setup")
            if value:
                env_fixed[name] = value
            else:
                env_asked.append(_input("env", name, variable, name))
    except _Blocked as e:
        return _Option("package", source, reason=e.reason)
    inputs += env_asked

    spec = f"{identifier}@{version}"
    lead = ["-y"] if command == "npx" else []

    def build(values: dict[str, str]) -> dict[str, Any]:
        env, secret_env = dict(env_fixed), {}
        for item in env_asked:
            given = values.get(item.id, "").strip() or item.default
            if not given:
                continue
            name = item.id.removeprefix("env:")
            if item.secret:
                secret_env[name] = int(given)
            else:
                env[name] = given
        words = [*lead, *runtime, spec, *(w for part in arguments for w in part(values))]
        return {"kind": "stdio", "command": command, "args": words, "env": env, "secret_env": secret_env}

    return _Option("package", f"{command} {spec}", command=command, inputs=inputs, build=build)


def _remote_option(remote: dict) -> _Option:
    url = _text(remote.get("url"))
    if remote.get("type") != "streamable-http":
        return _Option("remote", url, reason="sse" if remote.get("type") == "sse" else "other")
    variables = remote.get("variables") if isinstance(remote.get("variables"), dict) else {}
    named = _TEMPLATE_VARIABLE.findall(url)
    if any(n not in variables for n in named):
        return _Option("remote", url, reason="needs_setup")
    inputs = []
    for n in dict.fromkeys(named):
        spec = variables[n]
        item = _input("var", n, spec, n, secret=False)
        item.required = not item.default  # the address cannot be built without it
        inputs.append(item)

    bearer = False
    for header in remote.get("headers") or []:
        if not isinstance(header, dict):
            continue
        name = _text(header.get("name"))
        if name.lower() == "authorization":
            value = _text(header.get("value"))
            if value and not _BEARER_TEMPLATE.match(value):
                return _Option("remote", url, reason="headers")
            if not bearer:
                item = _input("bearer", "token", header, "Access token", secret=True)
                item.description = item.description or "Sent as a bearer token with every request."
                inputs.append(item)
                bearer = True
        elif header.get("isRequired"):  # an optional header is left out: the tool works without it
            return _Option("remote", url, reason="headers")

    def build(values: dict[str, str]) -> dict[str, Any]:
        address = url
        for item in inputs:
            if item.id.startswith("var:"):
                name = item.id.removeprefix("var:")
                address = address.replace("{" + name + "}", values.get(item.id, "").strip() or item.default)
        token = values.get("bearer:token", "").strip()
        return {"kind": "http", "url": address, "bearer_secret_id": int(token) if bearer and token else None}

    return _Option("remote", url, inputs=inputs, build=build)


def _options(entry: dict) -> list[_Option]:
    """Every way to run an entry, in the order they are preferred: packages that run inside the cell (the data stays
    there), npm before PyPI, then hosted addresses."""
    rank = {"npm": 0, "pypi": 1}
    packages = [p for p in entry.get("packages") or [] if isinstance(p, dict)]
    packages.sort(key=lambda p: rank.get(p.get("registryType"), 2))
    remotes = [r for r in entry.get("remotes") or [] if isinstance(r, dict)]
    remotes.sort(key=lambda r: r.get("type") != "streamable-http")
    version = _text(entry.get("version"))
    return [*(_package_option(p, version) for p in packages), *(_remote_option(r) for r in remotes)]


def ways_of(entry: dict) -> list[Way]:
    """Every way to run an entry, in preference order (see _options)."""
    return [o.way for o in _options(entry)]


def _choose(entry: dict, available: frozenset[str] | None) -> tuple[Way, _Option | None]:
    """The way to run an entry here and its full option (None when it cannot be run: there is nothing to build)."""
    options = _options(entry)
    way = pick_way([o.way for o in options], available)
    return way, next((o for o in options if o.way == way and not way.reason), None)


def reason_text(reason: str, command: str = "") -> str:
    if reason == "image_command":
        return f"The cell image has no '{command}', which this tool is started with."
    return REASONS.get(reason, "")


# ----- the public shape -----


def to_tool(entry: dict, available: frozenset[str] | None = None, note: str = "") -> RegistryTool:
    """An entry as the app lists it. `available` is the programs the image has (None when that is not known)."""
    way, option = _choose(entry, available)
    name = _text(entry.get("name"))
    repository = entry.get("repository") if isinstance(entry.get("repository"), dict) else {}
    return RegistryTool(
        name=name,
        title=display_title(name, _text(entry.get("title"))),
        description=_text(entry.get("description"))[:2000],
        version=_text(entry.get("version")),
        repository=_text(repository.get("url")),
        source=way.source,
        runs=way.runs,
        command=way.command,
        supported=not way.reason,
        reason=way.reason,
        reason_text=reason_text(way.reason, way.command),
        inputs=option.inputs if option else [],
        note=note,
    )


_GENERIC_NAMES = {"mcp", "server", "app", "api", "tools", "service", "mcp-server", "mcp_server"}


def display_title(name: str, title: str = "") -> str:
    """What a tool is called in a list: its title when the publisher gave one, else its name made readable
    (`notion-mcp-server` is Notion MCP Server; a generic last part such as `mcp` is replaced by the publisher's
    name, so com.notion/mcp is Notion)."""
    if title.strip():
        return title.strip()
    namespace, _, last = name.partition("/")
    base = last or namespace
    if base.lower() in _GENERIC_NAMES:
        parts = namespace.removeprefix("io.github.").split(".")
        base = parts[1] if len(parts) > 1 and not namespace.startswith("io.github.") else parts[0]
    words = [w for w in re.split(r"[-_\s]+", base) if w]
    return " ".join("MCP" if w.lower() == "mcp" else w[:1].upper() + w[1:] for w in words) or name


def tool_name(registry_name: str) -> str:
    """A tool's name (see McpIn) for a registry name: its last part, as a slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", registry_name.rsplit("/", 1)[-1].lower()).strip("-")[:40].strip("-")
    return slug if NAME.match(slug) else "tool"


def build_tool(entry: dict, values: dict[str, str], available: frozenset[str] | None = None) -> McpIn:
    """The tool for an entry once its inputs are answered. `values` is input id -> text (a key's id for a secret).
    Raises ValueError when the entry cannot be used, and MissingInput when a required input is empty."""
    way, option = _choose(entry, available)
    if option is None or option.build is None:
        raise ValueError(reason_text(way.reason, way.command) or REASONS["other"])
    missing = [
        i.label for i in option.inputs if i.required and not values.get(i.id, "").strip() and not i.default
    ]
    if missing:
        raise MissingInput("Fill in: " + ", ".join(missing))
    for item in option.inputs:  # a secret is a key's id, nothing else
        given = values.get(item.id, "").strip()
        if item.secret and given and not given.isdigit():
            raise ValueError(f"{item.label} must be a stored key")
        if item.choices and given and given not in item.choices:
            raise ValueError(f"{item.label} must be one of: {', '.join(item.choices)}")
    fields = option.build(values)
    return McpIn(
        name=tool_name(_text(entry.get("name"))),
        description=_text(entry.get("description"))[:2000],
        **fields,
    )


# ----- talking to the registry -----


class RegistryUnavailable(Exception):
    """The registry did not answer in a usable way (the message is for people)."""


_cache: dict[str, tuple[float, Any]] = {}
_runner_cache: dict[tuple[str, str], tuple[float, frozenset[str] | None]] = {}


async def fetch_json(url: str, params: dict[str, str] | None = None, who: str = "The MCP registry") -> Any:
    """GET an address and parse it (`who` names what is asked, in the messages). Redirects are not followed and a
    huge reply is cut off, because what answers is a third party."""
    import httpx  # imported here: only registry browsing needs it

    try:
        async with (
            httpx.AsyncClient(timeout=FETCH_SECONDS, follow_redirects=False) as client,
            client.stream("GET", url, params=params, headers={"Accept": "application/json"}) as r,
        ):
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                raise RegistryUnavailable(f"{who} answered with HTTP {r.status_code}.")
            raw = b""
            async for chunk in r.aiter_bytes():
                raw += chunk
                if len(raw) > MAX_REPLY * 4:
                    raise RegistryUnavailable(f"{who} sent a reply that was too large.")
    except httpx.TimeoutException:
        raise RegistryUnavailable(f"{who} did not answer within {FETCH_SECONDS} seconds.") from None
    except httpx.HTTPError as e:
        raise RegistryUnavailable(f"{who} could not be reached: {str(e)[:150] or type(e).__name__}") from e
    try:
        return json.loads(raw)
    except ValueError:
        raise RegistryUnavailable(f"{who} sent something that is not JSON.") from None


async def _cached(key: str, load: Callable[[], Any]) -> Any:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = await load()
    if len(_cache) >= MAX_CACHED:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic(), value)
    return value


def is_active(item: dict) -> bool:
    status = ((item.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}).get("status")
    return status in (None, "active")


async def get_entry(name: str, version: str = "latest") -> dict | None:
    """The entry for one registry name (None when the registry has no such server)."""
    if not REGISTRY_NAME.match(name):
        return None
    url = f"{REGISTRY_URL}/{quote(name, safe='')}/versions/{quote(version, safe='')}"
    body = await _cached("entry:" + url, lambda: fetch_json(url))
    if isinstance(body, dict) and isinstance(body.get("server"), dict) and is_active(body):
        return body["server"]
    return None


def featured_names() -> list[tuple[str, str]]:
    """(registry name, note) of the featured tools, in the order of featured_tools.yaml. A broken file is just an
    empty list: the search still works."""
    try:
        data = yaml.safe_load(FEATURED_FILE.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError):
        return []
    items = data.get("featured", []) if isinstance(data, dict) else data
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            item = {"name": item}
        if isinstance(item, dict) and REGISTRY_NAME.match(_text(item.get("name"))):
            out.append((_text(item["name"]), _text(item.get("note"))))
    return out


async def featured() -> list[tuple[dict, str]]:
    """(entry, note) of every featured tool the registry still has. Raises RegistryUnavailable when it could not be
    asked at all (an empty list then would look like a list with nothing in it)."""
    names = featured_names()
    found = await asyncio.gather(*(get_entry(n) for n, _ in names), return_exceptions=True)
    if found and all(isinstance(f, RegistryUnavailable) for f in found):
        raise found[0]
    return [(e, note) for e, (_, note) in zip(found, names, strict=True) if isinstance(e, dict)]


async def available_runners(image: str, docker_host: str = "") -> frozenset[str] | None:
    """Which of RUNNERS the image has, remembered for a while because a lookup starts a container. None when it
    cannot be known (see commands_in_image): then nothing is held against a tool."""
    key = (image, docker_host)
    hit = _runner_cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    found = await commands_in_image(image, set(RUNNERS), docker_host)
    result = frozenset(c for c, ok in found.items() if ok) if found is not None else None
    _runner_cache[key] = (time.monotonic(), result)
    return result
