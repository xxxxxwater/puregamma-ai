"""Alembic migration-chain integrity: single head, unique revisions, and a
connected upgrade path. No database connection is required."""

from __future__ import annotations

import ast
import os

VERSIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "packages", "database", "alembic", "versions"
)


def _parse_migration(path: str) -> tuple[str, str | None]:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    revision = None
    down_revision = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "revision":
                revision = ast.literal_eval(value)
            elif isinstance(target, ast.Name) and target.id == "down_revision":
                down_revision = ast.literal_eval(value)
    return revision, down_revision


def _load_graph() -> dict[str, str | None]:
    graph: dict[str, str | None] = {}
    for name in sorted(os.listdir(VERSIONS_DIR)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(VERSIONS_DIR, name)
        revision, down_revision = _parse_migration(path)
        assert revision is not None, f"{name} has no revision"
        assert revision not in graph, f"duplicate revision id: {revision}"
        graph[revision] = down_revision
    return graph


def test_migration_revisions_are_unique():
    graph = _load_graph()
    assert graph  # non-empty


def test_single_alembic_head():
    graph = _load_graph()
    revisions = set(graph)
    parents = {p for p in graph.values() if p is not None}
    heads = revisions - parents
    assert len(heads) == 1, f"expected exactly one head, got {sorted(heads)}"
    head = next(iter(heads))
    assert head == "0026_live_trading_control_plane"


def test_chain_is_connected_and_acyclic():
    graph = _load_graph()
    # Walk the chain from the head back to the root; detect missing parents
    # and cycles by visited-count (a cycle would require re-visiting a node).
    stack = ["0026_live_trading_control_plane"]
    visited: set[str] = set()
    while stack:
        revision = stack.pop()
        if revision in visited:
            raise AssertionError(f"cycle detected at {revision}")
        visited.add(revision)
        parent = graph.get(revision)
        if parent is None:
            continue
        assert parent in graph, f"revision {revision} points to missing parent {parent}"
        stack.append(parent)
    assert visited == set(graph), f"unreachable revisions: {sorted(set(graph) - visited)}"


def test_harness_migration_revises_portfolio_nav_snapshots():
    graph = _load_graph()
    assert graph["0025_harness_research"] == "0024_portfolio_nav_snapshots"


def test_live_trading_migration_revises_harness_research():
    graph = _load_graph()
    assert graph["0026_live_trading_control_plane"] == "0025_harness_research"


def test_migration_files_have_matching_revision_headers():
    """Every 00NN file declares a revision id matching its numeric prefix."""
    for name in sorted(os.listdir(VERSIONS_DIR)):
        if not name.endswith(".py"):
            continue
        prefix = name.split("_", 1)[0]
        revision, _ = _parse_migration(os.path.join(VERSIONS_DIR, name))
        assert revision.startswith(prefix), f"{name} prefix mismatch: {revision}"
