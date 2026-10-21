"""Keep shared operations independent of their HTTP and MCP adapters."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def imports(path: Path) -> set[str]:
    result = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
            result.update(f"{node.module}.{alias.name}" for alias in node.names)
    return result


def test_shared_operations_do_not_depend_on_http_controllers():
    operation_names = {
        "service",
        "operations",
        "queries",
        "creation",
        "access",
        "workspaces",
        "auth_service",
        "access_service",
        "skill_service",
    }
    violations = []
    for path in (APP / "features").rglob("*.py"):
        if path.stem not in operation_names:
            continue
        for module in imports(path):
            if module.startswith(("fastapi", "app.api", "app.main", "app.control")) or any(
                part == "routes" or part.endswith("_routes") for part in module.split(".")
            ):
                violations.append((str(path.relative_to(APP)), module))
    assert not violations


def test_execution_and_mcp_tools_do_not_call_http_controllers():
    for path in [*(APP / "execution").rglob("*.py"), APP / "control" / "tools.py"]:
        for module in imports(path):
            assert not module.startswith(("app.api", "app.main")), (path, module)
            assert not any(part == "routes" or part.endswith("_routes") for part in module.split(".")), (
                path,
                module,
            )


def test_persistence_does_not_import_features_or_transports():
    for path in (APP / "persistence").rglob("*.py"):
        for module in imports(path):
            assert not module.startswith(
                ("app.features", "app.execution", "app.api", "app.control", "app.main")
            ), (path, module)
