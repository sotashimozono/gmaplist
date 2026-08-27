# gmaplist

[![ci](https://github.com/sotashimozono/gmaplist/actions/workflows/ci.yml/badge.svg)](https://github.com/sotashimozono/gmaplist/actions/workflows/ci.yml)
[![codeql](https://github.com/sotashimozono/gmaplist/actions/workflows/codeql.yml/badge.svg)](https://github.com/sotashimozono/gmaplist/actions/workflows/codeql.yml)
![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Read a **Google Maps shared place list** and analyse who added what, where, and when.

Google publishes no API for saved lists, and a Takeout export keeps only the
title, note and URL of each place. The two fields that make a *collaborative*
list interesting — **the contributor and the timestamp of each entry** — are
dropped by every route Google documents, and by the third-party shared-list
scrapers, which return place details instead.

They are, however, present in the payload the Maps web client itself loads.
`gmaplist` reads that payload directly.

- No browser, no cookies, no API key, no account: one HTTP GET per list.
- No third-party dependencies. Python 3.10+ standard library only.
- Places without a Google-supplied address are located by point-in-polygon
  against prefecture boundaries, and every row records which method was used.

## Install

```sh
pip install -e .
```

Or just run it from a checkout: `python -m gmaplist ...`.

## Command line

```sh
gmaplist https://maps.app.goo.gl/xxxxxxxxxxxx --csv places.csv
```

```
  --csv PATH          write places to CSV (UTF-8 with BOM, opens in Excel)
  --json PATH         write list metadata and places to JSON
  --geojson PATH      write a point FeatureCollection
  --no-report         suppress the text report on stdout
  --anchor LAT,LNG    reference point: adds a distance_km column and a
                      reach section
  --tz-offset HOURS   offset used to display timestamps (default 9, JST)
  --no-geo            skip boundary lookup for places with no address
  --categories        EXPERIMENTAL: look up categories and group them
                      into genres (a second endpoint, see below)
  --refresh-geo       re-download the boundary file
  --hl / --gl         Google language and region (default ja / jp)
```

The report covers contributor totals and note habits, prefecture and regional
block distribution, additions per day, a contributor-by-region crosstab,
notes written on someone else's entry, and duplicate entries. With
`--anchor` it also reports how far the list reaches from that point and
where each contributor's picks cluster.

That last one is the question a saved list quietly begs: a group's list is
assumed to be places near the group. Measuring against a home coordinate is
what tells you whether it actually is.

Accepted inputs: a `maps.app.goo.gl` share link, a
`google.com/maps/placelists/list/<id>` URL, a `/maps/@/data=...!2s<id>!3e3`
URL, or a bare list id.

## Library

```python
import gmaplist
from gmaplist import analyze, export

plist, rows = gmaplist.load("https://maps.app.goo.gl/xxxxxxxxxxxx")

print(plist.title, plist.owner.name, len(plist))
for stat in analyze.by_contributor(rows):
    print(stat["count"], stat["name"], stat["top_regions"])

export.write_csv("places.csv", rows)
```

Each row is `{"place": Place, "prefecture": str | None, "prefecture_source":
str, "city": str, "country": str, "block": str}`. Places outside Japan carry a
`country` instead of a prefecture, taken from the last component of the address
Google returns, and their `block` is that country.

`prefecture_source` is one of `address`
(taken from the formatted address Google returned), `polygon` (the point falls
inside a prefecture outline), `nearest` (just offshore, snapped to the closest
outline within 0.15°), or `none`.

## Experimental: categories

A saved list records *where* people went, never *what kind of place* it was:
the payload carries no category at all. `gmaplist.experimental` fills that in
from the Maps search endpoint, queried by the feature ids the list already
gives us, and rolls Google's very fine-grained categories up into countable
genres.

```python
from gmaplist import experimental

details = experimental.fetch_details([r["place"].place_id for r in rows])
report = experimental.attach(rows, details)
print(report.matched, len(report.missing), report.review_coverage)
experimental.by_genre(rows)
```

It is separate, and named experimental, for three reasons.

- It reads a **different undocumented endpoint** from the rest of the package,
  with its own way of breaking.
- `genre_of` applies **opinionated Japanese-language rules**. They are
  keyword matches against Google's category strings, never against place
  names, so any classification can be checked against what Google actually
  said. Anything unmatched stays in an explicit unclassified bucket rather
  than being forced into the nearest genre, and `by_category` shows the raw
  categories for auditing. Pass your own `rules` for another language.
- Coverage is **not total**, and `attach` returns an `Enrichment` saying so.
  Streets, villages and other non-business entries have no category at all.

One trap worth stating plainly: `review_count` is usually absent. The endpoint
only fills it in for a browser session with cookies. Over plain HTTP it comes
back for a minority of places, and *which* minority is a property of the
request rather than of the places — so a fame statistic computed over it is
measuring the request, not the list. Check `Enrichment.review_coverage` before
using it.

## How it works

`GET /maps/preview/entitylist/getlist?pb=!1m4!1s<LIST_ID>!2e1!3m1!1e1!2e2!3e2!4i<PAGE_SIZE>`

The response is protobuf rendered as JSON: nested arrays with no field names.
The indices below were recovered by reading real responses, and are the one
part of this package that Google can break.

| Path | Meaning |
| --- | --- |
| `[0][0][0]` | list id |
| `[0][3]` | list owner `[name, avatar, user id]` |
| `[0][4]` / `[0][5]` | title / description |
| `[0][10]` / `[0][11]` | list created / updated `[seconds, nanos]` |
| `[0][12]` | number of places Google claims the list holds |
| `[0][8]` | the places |
| `…[2]` | place name |
| `…[3]` | note |
| `…[1][4]` | formatted address (often empty) |
| `…[1][5][2]`, `…[1][5][3]` | latitude, longitude |
| `…[1][6]` | place id, as two signed 64-bit halves |
| `…[1][7]` | Knowledge Graph mid |
| `…[9]` / `…[10]` | **entry added / updated** `[seconds, nanos]` |
| `…[12]` | **entry author** `[name, avatar, user id]` |
| `…[15][0]` | **note author** - not always the entry author |

Categories come from a second endpoint, `GET /search?tbm=map`, which accepts a bare list of feature ids: `pb=!7i<COUNT>` followed by `!72m2!1m1!1s<PLACE_ID>` per place, then `!77b1`. The page size must match the batch or the reply is silently truncated to twenty. Names sit at `[0][1][…][14][11]`, categories at `[…][14][13]`, rating at `[…][14][4][7]`.

`[0][12]` is compared against the number of places actually returned, and
`PlaceList.truncated` reports a mismatch.

## Caveats

- The endpoint is undocumented and unversioned. It occasionally answers with a
  payload that does not decode; `load()` retries before failing.
- `added_at` is when the entry record was created. A place moved in from
  another list gets a fresh timestamp, so a dense cluster of identical dates
  can mean a bulk import rather than a burst of activity.
- Only lists shared with "anyone with the link" are readable.
- The boundary file is
  [dataofjapan/land](https://github.com/dataofjapan/land), cached under the
  user cache directory. Non-Japanese places resolve to `abroad`.

## Contributing

`main` is protected and every change goes through a pull request with a
version bump. See [CONTRIBUTING.md](CONTRIBUTING.md), and
[.github/SECURITY.md](.github/SECURITY.md) for why exports and list ids
must stay out of the repository.

## License

MIT.

## Tests

```sh
python -m unittest discover -s tests
```

Offline: parsing, region resolution and aggregation run against inline
fixtures.
