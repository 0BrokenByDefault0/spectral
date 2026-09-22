"""Read access to the plugin catalog.

The catalog is a few dozen rows, so it is read once into memory and filtered there
rather than issuing a query per chain slot.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.db.seed import DEFAULT_DB
from app.models.schemas import PluginEntry, ProcessingCategory, Tier

#: Tiers to fall back to when a category has nothing at the requested tier.
#: A premium user can still use a free gate; nothing is worse than an empty slot.
_FALLBACK_ORDER: dict[Tier, tuple[Tier, ...]] = {
    Tier.FREE: (Tier.FREE, Tier.MID, Tier.PREMIUM),
    Tier.MID: (Tier.MID, Tier.FREE, Tier.PREMIUM),
    Tier.PREMIUM: (Tier.PREMIUM, Tier.MID, Tier.FREE),
}


class CatalogUnavailableError(RuntimeError):
    """Raised when the plugin database is missing or unreadable."""


@dataclass(frozen=True)
class Pick:
    """A selected plugin, plus how it was arrived at."""

    plugin: PluginEntry
    substituted_tier: bool = False
    reused: bool = False


class PluginCatalog:
    """Queryable view over the seeded plugin catalog."""

    def __init__(self, entries: list[PluginEntry]) -> None:
        self.entries = entries

    @classmethod
    def load(cls, db_path: Path = DEFAULT_DB) -> PluginCatalog:
        if not Path(db_path).exists():
            raise CatalogUnavailableError(
                f"no plugin database at {db_path}; run `python -m app.db.seed`"
            )
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute("SELECT * FROM plugins").fetchall()
        except sqlite3.Error as exc:
            raise CatalogUnavailableError(f"could not read {db_path}: {exc}") from exc

        return cls([_entry_from_row(row) for row in rows])

    def select(
        self,
        category: ProcessingCategory,
        tier: Tier,
        preferred_tags: tuple[str, ...] = (),
        excluded_tags: tuple[str, ...] = (),
        exclude: frozenset[str] = frozenset(),
    ) -> Pick | None:
        """Best plugin for a chain slot.

        Ranking, in order: how many of `preferred_tags` it carries, then rating, then
        the lower price. `excluded_tags` rules a plugin out of the slot entirely.
        `exclude` holds names already used in this chain, which are skipped unless
        nothing else fits — repeating a plugin is better than filling a slot with a
        tool that does not suit it.
        """
        for index, candidate_tier in enumerate(_FALLBACK_ORDER[tier]):
            pool = [
                e
                for e in self.entries
                if e.category is category
                and e.tier is candidate_tier
                and not _has_any_tag(e, excluded_tags)
            ]
            if not pool:
                continue
            fresh = [e for e in pool if e.name not in exclude]
            best = _rank(fresh or pool, preferred_tags)
            return Pick(
                plugin=best,
                substituted_tier=index > 0,
                reused=best.name in exclude,
            )
        return None

    def by_category(self, category: ProcessingCategory) -> list[PluginEntry]:
        return [e for e in self.entries if e.category is category]


def _has_any_tag(entry: PluginEntry, tags: tuple[str, ...]) -> bool:
    lowered = {tag.lower() for tag in entry.tags}
    return any(tag.lower() in lowered for tag in tags)


def _rank(pool: list[PluginEntry], preferred_tags: tuple[str, ...]) -> PluginEntry:
    wanted = {tag.lower() for tag in preferred_tags}
    return max(
        pool,
        key=lambda e: (
            len(wanted & {tag.lower() for tag in e.tags}),
            e.rating,
            -e.price_usd,
        ),
    )


def _entry_from_row(row: sqlite3.Row) -> PluginEntry:
    data = dict(row)
    data["tags"] = json.loads(data["tags"])
    return PluginEntry.model_validate(data)
