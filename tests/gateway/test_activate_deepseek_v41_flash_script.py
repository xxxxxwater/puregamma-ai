"""The Gateway activation script must actually run.

It is the only way `deepseek-flash` becomes routable in production, and it is
executed by hand inside a container during a deployment. A missing import or a
renamed column has to fail here rather than at 3am in a deployment window.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from apps.api.config import DEEPSEEK_MODEL_FLASH
from packages.database.models import GatewayModel, GatewayPriceRevision, GatewayProvider
from packages.gateway.catalog import provider_models

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "activate_deepseek_v41_flash.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("activate_deepseek_v41_flash", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["activate_deepseek_v41_flash"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_activation_script_imports_cleanly():
    """Importing executes every module-level import and decorator."""
    module = _load_script_module()

    assert module.TARGET_PROVIDER == "deepseek"
    # The functions the script calls must all exist on the module.
    for name in ("provider_catalog", "bootstrap_gateway_catalog", "sync_provider_metadata", "approve_price_revision"):
        assert hasattr(module, name), f"{name} is not imported"


def test_activation_script_only_references_real_orm_columns():
    """A renamed column would otherwise surface as a runtime crash mid-deploy.

    The script runs by hand during a deployment window, so every ORM attribute
    it touches is checked statically -- including ones on the reporting path
    that a `--dry-run` smoke test would never execute.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    mapper_classes = {
        "GatewayModel": GatewayModel,
        "GatewayPriceRevision": GatewayPriceRevision,
        "GatewayProvider": GatewayProvider,
    }
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            continue
        model = mapper_classes.get(node.value.id)
        # hasattr() is the exact question the AST reference asks: does this ORM
        # class expose this Python attribute name?
        if model is not None and not hasattr(model, node.attr):
            problems.append(f"{node.value.id}.{node.attr} (line {node.lineno})")

    assert problems == [], f"unknown ORM attributes referenced: {problems}"


def test_activation_script_attributes_match_the_orm_exactly():
    """Guard the guard: the checker must reject a known-bad attribute name."""
    # The price columns are exposed as `..._json` attributes over the plain
    # database column names. Using the database column name as an attribute is
    # the mistake that broke the first production run of this script, so these
    # four assertions are what makes the static check above meaningful.
    assert hasattr(GatewayPriceRevision, "official_prices_json")
    assert hasattr(GatewayPriceRevision, "final_prices_json")
    assert not hasattr(GatewayPriceRevision, "official_prices")
    assert not hasattr(GatewayPriceRevision, "final_prices")


def test_activation_script_targets_the_configured_catalog_models():
    module = _load_script_module()
    wanted = module._catalog_models()

    assert DEEPSEEK_MODEL_FLASH in wanted
    catalog_ids = {model.public_id for model in provider_models("deepseek")}
    assert set(wanted) <= catalog_ids


def test_activation_script_help_runs_without_a_database(monkeypatch, capsys):
    """`--dry-run` must report catalog state without needing provider keys."""
    module = _load_script_module()
    monkeypatch.setattr(sys, "argv", ["activate", "--dry-run"])
    monkeypatch.setattr(module, "SessionLocal", lambda: _NoopSession())

    assert module.main() == 0
    out = capsys.readouterr().out
    assert DEEPSEEK_MODEL_FLASH in out
    assert "dry run" in out


class _NoopSession:
    """Enough of a Session for the read-only dry-run path."""

    def query(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

    def close(self):
        return None
