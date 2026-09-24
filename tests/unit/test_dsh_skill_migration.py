from packages.skills.dsh_migration import legacy_slug_to_dsh_name, migration_catalog


def test_known_legacy_skill_names_are_stable():
    assert legacy_slug_to_dsh_name("market_research") == "market-research"
    assert legacy_slug_to_dsh_name("harness_deep_research") == "harness-deep-research"


def test_generic_underscore_slug_is_kebab_case():
    assert legacy_slug_to_dsh_name("custom_research") == "custom-research"


def test_catalog_has_unique_dsh_names():
    rows = migration_catalog()
    assert len({row.dsh_name for row in rows}) == len(rows)
