"""Load `data/plugins.json` into the SQLite plugin catalog.

    python -m app.db.seed              # rebuild app/db/plugins.db from data/plugins.json
    python -m app.db.seed --check      # validate the JSON without touching the database

`plugins.json` is the source of truth; the database is a generated, checked-in
artifact and gets dropped and rebuilt on every run.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError

from app.models.schemas import PluginEntry

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = BACKEND_ROOT.parent / "data" / "plugins.json"
DEFAULT_DB = BACKEND_ROOT / "app" / "db" / "plugins.db"

SCHEMA = """
CREATE TABLE plugins (
    name         TEXT NOT NULL,
    vendor       TEXT NOT NULL,
    category     TEXT NOT NULL,
    tier         TEXT NOT NULL,
    price_usd    REAL NOT NULL,
    price        TEXT NOT NULL,
    purchase_url TEXT,
    rating       REAL NOT NULL,
    tags         TEXT NOT NULL,
    why          TEXT NOT NULL,
    PRIMARY KEY (name, category)
);
CREATE INDEX plugins_by_slot ON plugins (category, tier, rating DESC);
"""


class CatalogError(ValueError):
    """Raised when the catalog JSON is malformed or internally inconsistent."""


def load_catalog(json_path: Path = DEFAULT_JSON) -> list[PluginEntry]:
    """Read and validate the catalog. Raises `CatalogError` on anything wrong."""
    try:
        raw = json.loads(json_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"could not read {json_path}: {exc}") from exc

    try:
        entries = [PluginEntry.model_validate(row) for row in raw["plugins"]]
    except KeyError as exc:
        raise CatalogError(f"{json_path} has no 'plugins' array") from exc
    except ValidationError as exc:
        raise CatalogError(f"invalid plugin entry in {json_path}: {exc}") from exc

    _check_unique(entries)
    _check_tier_prices(entries)
    return entries


def _check_unique(entries: list[PluginEntry]) -> None:
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry.name, entry.category.value)
        if key in seen:
            raise CatalogError(f"duplicate entry: {entry.name} in {entry.category.value}")
        seen.add(key)


#: Price brackets the spec defines for each tier, in USD.
TIER_PRICE_RANGES = {
    "FREE": (0.0, 0.0),
    "MID": (1.0, 100.0),
    "PREMIUM": (100.01, float("inf")),
}


def _check_tier_prices(entries: list[PluginEntry]) -> None:
    for entry in entries:
        low, high = TIER_PRICE_RANGES[entry.tier.value]
        if not low <= entry.price_usd <= high:
            raise CatalogError(
                f"{entry.name} is {entry.tier.value} but costs ${entry.price_usd:.2f}, "
                f"outside ${low:.2f}-${high:.2f}"
            )


def seed(json_path: Path = DEFAULT_JSON, db_path: Path = DEFAULT_DB) -> int:
    """Rebuild the database from the JSON catalog. Returns the number of rows written."""
    entries = load_catalog(json_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT INTO plugins "
            "(name, vendor, category, tier, price_usd, price, purchase_url, rating, tags, why) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e.name,
                    e.vendor,
                    e.category.value,
                    e.tier.value,
                    e.price_usd,
                    e.price,
                    e.purchase_url,
                    e.rating,
                    json.dumps(e.tags),
                    e.why,
                )
                for e in entries
            ],
        )
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed", description="Seed the plugin catalog")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--check", action="store_true", help="Validate the JSON and write nothing"
    )
    args = parser.parse_args(argv)

    try:
        if args.check:
            entries = load_catalog(args.json)
            print(f"{args.json}: {len(entries)} plugins, valid")
            print(_coverage(entries))
            return 0
        written = seed(args.json, args.db)
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"wrote {written} plugins to {args.db}")
    return 0


def _coverage(entries: list[PluginEntry]) -> str:
    """A category x tier count table, so gaps in the catalog are visible."""
    tiers = ["FREE", "MID", "PREMIUM"]
    counts: dict[str, dict[str, int]] = {}
    for entry in entries:
        counts.setdefault(entry.category.value, dict.fromkeys(tiers, 0))
        counts[entry.category.value][entry.tier.value] += 1

    lines = [f"{'category':<18}" + "".join(f"{tier:>9}" for tier in tiers)]
    for category, row in sorted(counts.items()):
        lines.append(f"{category:<18}" + "".join(f"{row[tier]:>9}" for tier in tiers))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
