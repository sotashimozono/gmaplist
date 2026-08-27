"""Command line entry point."""

from __future__ import annotations

import argparse
import contextlib
import sys

from . import __version__, export, load
from .fetch import ListFetchError
from .report import render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gmaplist",
        description="Analyse a Google Maps shared place list.",
    )
    p.add_argument("source", help="share link, list URL or bare list id")
    p.add_argument("--csv", metavar="PATH", help="write places to a CSV file")
    p.add_argument("--json", metavar="PATH", help="write list and places to JSON")
    p.add_argument("--geojson", metavar="PATH", help="write a point FeatureCollection")
    p.add_argument("--no-report", action="store_true", help="suppress the text report")
    p.add_argument(
        "--anchor",
        metavar="LAT,LNG",
        help=(
            "reference point; adds a distance_km column and a reach section "
            "answering whether the list is actually about places near you"
        ),
    )
    p.add_argument(
        "--tz-offset",
        type=float,
        default=9.0,
        metavar="HOURS",
        help="UTC offset used to display timestamps (default: 9, JST)",
    )
    p.add_argument(
        "--no-geo",
        action="store_true",
        help="skip boundary lookup; places without an address stay unresolved",
    )
    p.add_argument(
        "--refresh-geo", action="store_true", help="re-download the boundary file"
    )
    p.add_argument("--hl", default="ja", help="Google UI language (default: ja)")
    p.add_argument("--gl", default="jp", help="Google region (default: jp)")
    p.add_argument("--version", action="version", version=f"gmaplist {__version__}")
    return p


def _parse_anchor(text: str) -> tuple[float, float]:
    parts = text.replace(" ", "").split(",")
    if len(parts) != 2:
        raise ValueError("expected LAT,LNG")
    lat, lng = (float(v) for v in parts)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError("coordinates out of range")
    return lat, lng


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    anchor = None
    if args.anchor:
        try:
            anchor = _parse_anchor(args.anchor)
        except ValueError as exc:
            print(f"gmaplist: --anchor {args.anchor!r}: {exc}", file=sys.stderr)
            return 2

    try:
        plist, rows = load(
            args.source,
            hl=args.hl,
            gl=args.gl,
            geo=not args.no_geo,
            refresh_geo=args.refresh_geo,
        )
    except (ListFetchError, ValueError) as exc:
        print(f"gmaplist: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print("gmaplist: the list is empty or not publicly shared", file=sys.stderr)
        return 1

    if args.csv:
        export.write_csv(args.csv, rows, args.tz_offset, anchor)
        print(f"wrote {args.csv} ({len(rows)} places)", file=sys.stderr)
    if args.json:
        export.write_json(args.json, plist, rows, args.tz_offset, anchor)
        print(f"wrote {args.json}", file=sys.stderr)
    if args.geojson:
        export.write_geojson(args.geojson, rows, args.tz_offset, anchor)
        print(f"wrote {args.geojson}", file=sys.stderr)

    if not args.no_report:
        text = render(plist, rows, args.tz_offset, anchor=anchor)
        # Console encodings on Windows are frequently not UTF-8.
        stream = sys.stdout
        if getattr(stream, "encoding", "").lower() not in ("utf-8", "utf8"):
            with contextlib.suppress(AttributeError, OSError):
                stream.reconfigure(encoding="utf-8")
        print(text)
    return 0
