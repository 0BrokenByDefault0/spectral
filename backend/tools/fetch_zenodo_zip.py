"""Pull selected files out of a Zenodo archive without downloading the archive.

Some of the useful corpora ship as one large zip — URSing is 16.8 GB for 65 songs —
when the calibration only needs a subset. Zenodo serves HTTP range requests, so this
reads the zip's central directory from the end of the file, then fetches and inflates
only the members that match.

    python -m tools.fetch_zenodo_zip 6404999 data.zip --match Vocal.wav --limit 30 \
        --out ~/corpus/ursing-vocals

Attribution for whatever is fetched is written next to it, since the audio itself is
never committed.
"""

from __future__ import annotations

import argparse
import json
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

TIMEOUT = 120
#: The central directory lives at the end; this much tail is plenty to find it.
TAIL_BYTES = 128 * 1024
#: A fetch is dozens of sequential range requests, so a transient reset partway through
#: is expected rather than exceptional.
ATTEMPTS = 4


@dataclass
class Member:
    name: str
    compressed_size: int
    uncompressed_size: int
    method: int
    local_offset: int


def _retrying(what: str, call):
    """Run `call`, retrying transient transport failures with a growing backoff."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return call()
        except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError) as exc:
            if attempt == ATTEMPTS:
                raise
            delay = 2**attempt
            print(f"  {what} failed ({exc}); retrying in {delay}s", file=sys.stderr, flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def _get(url: str, start: int, end: int) -> bytes:
    def once() -> bytes:
        request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if response.status != 206:
                raise RuntimeError("the server ignored the range request")
            data = response.read()
        if len(data) != end - start + 1:
            raise ConnectionError(f"short read: {len(data)} of {end - start + 1} bytes")
        return data

    return _retrying(f"range {start}-{end}", once)


def _size(url: str) -> int:
    def once() -> int:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return int(response.headers["Content-Length"])

    return _retrying("size", once)


def read_directory(url: str) -> list[Member]:
    """The zip's central directory, read from the end of the remote file."""
    size = _size(url)
    tail = _get(url, max(0, size - TAIL_BYTES), size - 1)

    zip64 = tail.rfind(b"PK\x06\x06")
    if zip64 >= 0:
        directory_size, directory_offset = struct.unpack("<QQ", tail[zip64 + 40 : zip64 + 56])
    else:
        end = tail.rfind(b"PK\x05\x06")
        if end < 0:
            raise RuntimeError("no zip central directory found")
        directory_size, directory_offset = struct.unpack("<II", tail[end + 12 : end + 20])

    raw = _get(url, directory_offset, directory_offset + directory_size - 1)
    members, position = [], 0
    while position < len(raw) - 4 and raw[position : position + 4] == b"PK\x01\x02":
        method = struct.unpack("<H", raw[position + 10 : position + 12])[0]
        compressed, uncompressed = struct.unpack("<II", raw[position + 20 : position + 28])
        name_len, extra_len, comment_len = struct.unpack("<HHH", raw[position + 28 : position + 34])
        local = struct.unpack("<I", raw[position + 42 : position + 46])[0]
        name = raw[position + 46 : position + 46 + name_len].decode("utf-8", "replace")
        extra = raw[position + 46 + name_len : position + 46 + name_len + extra_len]

        # Past 4 GB the 32-bit fields hold 0xFFFFFFFF and the real values live in the
        # zip64 extra field, in a fixed order, each present only if its field overflowed.
        if 0xFFFFFFFF in (compressed, uncompressed, local):
            uncompressed, compressed, local = _zip64_values(
                extra, uncompressed, compressed, local
            )

        members.append(Member(name, compressed, uncompressed, method, local))
        position += 46 + name_len + extra_len + comment_len
    return members


def _zip64_values(
    extra: bytes, uncompressed: int, compressed: int, local: int
) -> tuple[int, int, int]:
    position = 0
    while position + 4 <= len(extra):
        header_id, size = struct.unpack("<HH", extra[position : position + 4])
        body = extra[position + 4 : position + 4 + size]
        if header_id == 0x0001:
            cursor = 0
            for index, value in enumerate((uncompressed, compressed, local)):
                if value != 0xFFFFFFFF or cursor + 8 > len(body):
                    continue
                real = struct.unpack("<Q", body[cursor : cursor + 8])[0]
                cursor += 8
                if index == 0:
                    uncompressed = real
                elif index == 1:
                    compressed = real
                else:
                    local = real
            break
        position += 4 + size
    return uncompressed, compressed, local


def extract(url: str, member: Member, target: Path) -> None:
    """Fetch and inflate one member."""
    # The local header repeats the name and extra field, and its extra field length can
    # differ from the central directory's, so read the header before the payload.
    header = _get(url, member.local_offset, member.local_offset + 29)
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    start = member.local_offset + 30 + name_len + extra_len
    payload = _get(url, start, start + member.compressed_size - 1)

    if member.method == 0:
        data = payload
    elif member.method == 8:
        data = zlib.decompress(payload, -zlib.MAX_WBITS)
    else:
        raise RuntimeError(f"{member.name}: unsupported compression method {member.method}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def record_metadata(record_id: str) -> dict:
    with urllib.request.urlopen(
        f"https://zenodo.org/api/records/{record_id}", timeout=TIMEOUT
    ) as response:
        return json.load(response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fetch_zenodo_zip", description=__doc__)
    parser.add_argument("record", help="Zenodo record id, e.g. 6404999")
    parser.add_argument("archive", help="Name of the zip in that record, e.g. data.zip")
    parser.add_argument("--match", action="append", required=True, help="Substring to match")
    parser.add_argument("--limit", type=int, help="Stop after this many files")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    record = record_metadata(args.record)
    files = {f["key"]: f for f in record["files"]}
    if args.archive not in files:
        print(f"{args.archive} is not in record {args.record}", file=sys.stderr)
        return 1
    url = files[args.archive]["links"]["self"]

    print(f"reading the index of {args.archive}")
    members = [
        m
        for m in read_directory(url)
        if any(fragment in m.name for fragment in args.match) and "__MACOSX" not in m.name
    ]
    members.sort(key=lambda m: m.name)
    if args.limit:
        members = members[: args.limit]

    if not members:
        print("nothing matched", file=sys.stderr)
        return 1

    total = sum(m.uncompressed_size for m in members) / 1e9
    print(f"fetching {len(members)} files ({total:.2f} GB uncompressed)")
    for index, member in enumerate(members, start=1):
        target = args.out / Path(member.name).parent.name / Path(member.name).name
        if target.exists():
            continue
        extract(url, member, target)
        print(f"  {index}/{len(members)} {member.name}", flush=True)

    licence = (record["metadata"].get("license") or {}).get("id", "unknown")
    (args.out / "SOURCE.json").write_text(
        json.dumps(
            {
                "zenodo_record": args.record,
                "title": record["metadata"]["title"],
                "license": licence,
                "archive": args.archive,
                "files": [m.name for m in members],
            },
            indent=2,
        )
    )
    print(f"\n{len(members)} files in {args.out} (licence: {licence})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
