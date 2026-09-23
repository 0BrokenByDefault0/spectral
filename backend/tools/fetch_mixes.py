"""Fetch a corpus of Creative Commons full mixes from the Internet Archive.

The detector needs labelled full mixes to score against, and the vocal datasets only
supply the other class. This pulls one track per netlabel release, writes the audio to
`--out`, and records identifier, title and licence for every file in a manifest so the
corpus behind the constants is auditable and reproducible.

    python -m tools.fetch_mixes --out ~/corpus/mixes --count 40

Audio is not committed to the repository — only the manifest is.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SEARCH = "https://archive.org/advancedsearch.php"
METADATA = "https://archive.org/metadata/"
DOWNLOAD = "https://archive.org/download/"

#: Netlabel releases skew electronic, so ask for a spread of genres rather than
#: whatever the first page happens to hold.
QUERIES = (
    "collection:netlabels AND subject:rock",
    "collection:netlabels AND subject:hiphop",
    "collection:netlabels AND subject:pop",
    "collection:netlabels AND subject:folk",
    "collection:netlabels AND subject:electronic",
    "collection:netlabels AND subject:jazz",
)

AUDIO_FORMATS = ("VBR MP3", "128Kbps MP3", "MP3", "Flac", "24bit Flac")
TIMEOUT = 60

#: Only licences that permit commercial use. Constants tuned on this corpus ship in a
#: product, so an NC or ND release is not usable here however convenient it is — the same
#: reason MUSDB18, which would otherwise be the obvious corpus, is not used.
ALLOWED_LICENCES = ("/by/", "/by-sa/", "/publicdomain/zero", "/publicdomain/mark", "/cc0")


def licence_is_usable(url: str) -> bool:
    return any(fragment in url for fragment in ALLOWED_LICENCES)


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        return json.load(response)


def search(query: str, rows: int) -> list[str]:
    """Identifiers whose licence permits commercial use.

    Only about one netlabel release in eight qualifies, so the licence comes back with
    the search results and is filtered here — fetching per-item metadata first would
    mean hundreds of requests to find a handful of usable releases.
    """
    params = urllib.parse.urlencode(
        [
            ("q", f"{query} AND licenseurl:[* TO *]"),
            ("fl[]", "identifier"),
            ("fl[]", "licenseurl"),
            ("rows", rows),
            ("page", 1),
            ("output", "json"),
        ]
    )
    docs = fetch_json(f"{SEARCH}?{params}")["response"]["docs"]

    usable = []
    for doc in docs:
        licence = doc.get("licenseurl", "")
        if isinstance(licence, list):
            licence = licence[0] if licence else ""
        if licence_is_usable(licence):
            usable.append(doc["identifier"])
    return usable


def pick_track(identifier: str) -> tuple[str, dict] | None:
    """One audio file from a release, with the metadata needed for attribution."""
    try:
        meta = fetch_json(f"{METADATA}{identifier}")
    except Exception as exc:
        print(f"  {identifier}: metadata failed ({exc})", file=sys.stderr)
        return None

    licence = meta.get("metadata", {}).get("licenseurl", "")
    if not licence_is_usable(licence):
        return None

    for wanted in AUDIO_FORMATS:
        for entry in meta.get("files", []):
            if entry.get("format") == wanted and entry.get("name"):
                return entry["name"], {
                    "identifier": identifier,
                    "title": meta["metadata"].get("title", ""),
                    "creator": meta["metadata"].get("creator", ""),
                    "license": licence,
                    "format": wanted,
                    "file": entry["name"],
                }
    return None


def download(identifier: str, name: str, target: Path) -> bool:
    url = DOWNLOAD + identifier + "/" + urllib.parse.quote(name)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            target.write_bytes(response.read())
    except Exception as exc:
        print(f"  {identifier}: download failed ({exc})", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fetch_mixes", description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=40, help="Tracks to collect in total")
    parser.add_argument(
        "--query",
        action="append",
        help="Search query to use instead of the built-in genre spread; repeatable",
    )
    parser.add_argument(
        "--scan", type=int, default=400, help="Search results to scan per genre query"
    )
    parser.add_argument(
        "--manifest", type=Path, help="Where to write attribution (default: <out>/manifest.json)"
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest or args.out / "manifest.json"
    queries = tuple(args.query) if args.query else QUERIES
    per_query = max(2, args.count // len(queries) + 1)

    collected: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        if len(collected) >= args.count:
            break
        print(f"searching: {query}")
        for identifier in search(query, args.scan):
            if len(collected) >= args.count or identifier in seen:
                continue
            seen.add(identifier)

            picked = pick_track(identifier)
            if picked is None:
                continue
            name, attribution = picked

            target = args.out / f"{identifier}{Path(name).suffix.lower()}"
            if not download(identifier, name, target):
                continue

            attribution["saved_as"] = target.name
            attribution["query"] = query
            attribution["size_bytes"] = target.stat().st_size
            collected.append(attribution)
            print(f"  {len(collected):>3}. {identifier} ({attribution['license']})")

            if sum(1 for c in collected if c["query"] == query) >= per_query:
                break

    manifest_path.write_text(json.dumps(collected, indent=2))
    print(f"\n{len(collected)} tracks in {args.out}, attribution in {manifest_path}")
    return 0 if collected else 1


if __name__ == "__main__":
    raise SystemExit(main())
