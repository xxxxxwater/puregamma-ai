"""Acceptance-layer pytest configuration.

The default suite (``pytest`` / ``pytest tests``) NEVER runs live-load tests:
tests marked ``@pytest.mark.load`` are deselected unless ``--runload`` is
passed explicitly.

Run the opt-in load smoke (Scenario K scale smoke) with:

    .venv/Scripts/python.exe -m pytest tests/acceptance -q --runload

Nothing here changes pytest.ini: ``testpaths`` and default ``addopts`` stay
as they are; this hook only deselects load-marked items collected under the
default invocation.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--runload",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.load (opt-in live-load / scale smokes)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "load: opt-in live-load / scale tests; run explicitly with --runload",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runload"):
        return
    skip_load = pytest.mark.skip(reason="load test deselected: pass --runload to opt in")
    for item in items:
        if "load" in item.keywords:
            item.add_marker(skip_load)
