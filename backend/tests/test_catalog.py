"""The shipped catalog, the seed script's validation, and plugin selection."""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.db import seed
from app.db.repository import CatalogUnavailableError, PluginCatalog
from app.models.schemas import ProcessingCategory, Tier

TIERS = (Tier.FREE, Tier.MID, Tier.PREMIUM)


@pytest.fixture(scope="module")
def entries():
    return seed.load_catalog()


@pytest.fixture(scope="module")
def catalog(entries):
    return PluginCatalog(entries)


def test_shipped_catalog_is_valid_and_large_enough(entries):
    assert 60 <= len(entries) <= 80, "the spec asks for 60-80 plugins"


def test_every_category_is_covered_at_every_tier(entries):
    for category in ProcessingCategory:
        for tier in TIERS:
            matching = [e for e in entries if e.category is category and e.tier is tier]
            assert matching, f"no {tier.value} plugin for {category.value}"


def test_free_plugins_cost_nothing(entries):
    assert all(e.price_usd == 0 for e in entries if e.tier is Tier.FREE)


def test_every_plugin_has_a_reason_and_a_link(entries):
    for entry in entries:
        assert entry.why.strip(), f"{entry.name} has no why"
        assert entry.purchase_url and entry.purchase_url.startswith("https://")


def test_seed_writes_a_readable_database(tmp_path):
    db = tmp_path / "plugins.db"
    written = seed.seed(db_path=db)
    assert written == len(seed.load_catalog())

    loaded = PluginCatalog.load(db)
    assert len(loaded.entries) == written
    assert {e.name for e in loaded.entries} == {e.name for e in seed.load_catalog()}


def test_seeding_twice_replaces_rather_than_duplicates(tmp_path):
    db = tmp_path / "plugins.db"
    seed.seed(db_path=db)
    seed.seed(db_path=db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM plugins").fetchone()[0] == len(
            seed.load_catalog()
        )


def test_a_missing_database_is_a_clean_failure(tmp_path):
    with pytest.raises(CatalogUnavailableError, match="app.db.seed"):
        PluginCatalog.load(tmp_path / "nope.db")


def write_catalog(tmp_path, plugins):
    path = tmp_path / "plugins.json"
    path.write_text(json.dumps({"plugins": plugins}))
    return path


BASE = {
    "name": "Test EQ",
    "vendor": "Test",
    "category": "EQ",
    "tier": "FREE",
    "price_usd": 0,
    "price": "Free",
    "purchase_url": "https://example.test",
    "rating": 4.0,
    "tags": [],
    "why": "because",
}


def test_duplicate_entries_are_rejected(tmp_path):
    path = write_catalog(tmp_path, [BASE, dict(BASE)])
    with pytest.raises(seed.CatalogError, match="duplicate"):
        seed.load_catalog(path)


def test_the_same_plugin_may_appear_in_two_categories(tmp_path):
    path = write_catalog(tmp_path, [BASE, dict(BASE, category="DE_ESS")])
    assert len(seed.load_catalog(path)) == 2


def test_a_price_outside_its_tier_is_rejected(tmp_path):
    path = write_catalog(tmp_path, [dict(BASE, tier="MID", price_usd=250, price="$250")])
    with pytest.raises(seed.CatalogError, match="outside"):
        seed.load_catalog(path)


def test_an_unknown_category_is_rejected(tmp_path):
    path = write_catalog(tmp_path, [dict(BASE, category="VIBES")])
    with pytest.raises(seed.CatalogError, match="invalid plugin entry"):
        seed.load_catalog(path)


def test_selection_prefers_the_requested_tier(catalog):
    for tier in TIERS:
        pick = catalog.select(ProcessingCategory.EQ, tier)
        assert pick is not None
        assert pick.plugin.tier is tier
        assert not pick.substituted_tier


def test_selection_prefers_matching_tags(catalog):
    dereverb = catalog.select(
        ProcessingCategory.NOISE_REDUCTION, Tier.MID, preferred_tags=("dereverb",)
    )
    assert "dereverb" in dereverb.plugin.tags

    denoise = catalog.select(
        ProcessingCategory.NOISE_REDUCTION, Tier.MID, preferred_tags=("denoise",)
    )
    assert "denoise" in denoise.plugin.tags
    assert denoise.plugin.name != dereverb.plugin.name


def test_excluded_tags_rule_a_plugin_out(catalog):
    without = catalog.select(ProcessingCategory.EQ, Tier.PREMIUM, excluded_tags=("cut-only",))
    assert "cut-only" not in without.plugin.tags


def test_already_used_plugins_are_skipped(catalog):
    first = catalog.select(ProcessingCategory.REVERB, Tier.MID)
    second = catalog.select(
        ProcessingCategory.REVERB, Tier.MID, exclude=frozenset({first.plugin.name})
    )
    assert second.plugin.name != first.plugin.name
    assert not second.reused


def test_a_used_plugin_comes_back_when_it_is_the_only_option(catalog):
    only = catalog.by_category(ProcessingCategory.GATE)
    names = frozenset(e.name for e in only if e.tier is Tier.PREMIUM)
    pick = catalog.select(ProcessingCategory.GATE, Tier.PREMIUM, exclude=names)
    assert pick.plugin.name in names
    assert pick.reused


def test_selection_falls_back_to_another_tier_when_a_slot_is_empty():
    sparse = PluginCatalog(
        [e for e in seed.load_catalog() if not (e.category is ProcessingCategory.GATE and e.tier is Tier.PREMIUM)]
    )
    pick = sparse.select(ProcessingCategory.GATE, Tier.PREMIUM)
    assert pick is not None
    assert pick.plugin.tier is not Tier.PREMIUM
    assert pick.substituted_tier


def test_selection_returns_nothing_for_an_empty_category():
    empty = PluginCatalog([e for e in seed.load_catalog() if e.category is not ProcessingCategory.DELAY])
    assert empty.select(ProcessingCategory.DELAY, Tier.FREE) is None
