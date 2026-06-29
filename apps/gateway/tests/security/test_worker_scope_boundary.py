"""Static security-boundary tests for worker JWT scopes."""

import ast
from pathlib import Path


def test_worker_dependency_is_not_used_by_admin_routes() -> None:
    admin_source = Path("apps/gateway/src/orbi_gateway/routes/admin.py").read_text(encoding="utf-8")
    tree = ast.parse(admin_source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "WorkerDep" not in imported_names
