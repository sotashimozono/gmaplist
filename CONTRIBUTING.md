# Contributing

## The flow

`main` is protected. Every change — including changes by the repository owner —
goes through a pull request, and the branch must be up to date with `main`
before it can merge.

Required checks: `lint`, `test` on 3.10 / 3.11 / 3.12 / 3.13, `package`,
`version-check`, `typos`.

## Before you open a PR

```sh
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
python -m unittest discover -s tests
```

Bump `[project].version` in `pyproject.toml`. This is enforced: `version-check`
compares against the base branch and fails if the version did not move
forward. There is no published artifact here, so the version is the only
durable marker that one build differs from the last.

## Never commit

A share link, a list id, a contributor name, or a real export. A list id alone
grants anyone who holds it read access to the whole list, contributor names
included. See `.github/SECURITY.md`.

The test suite is offline and fixture-based so that contributing never
requires pointing the tool at a real list.

## Touching the decoder

`gmaplist/model.py` maps unnamed array indices onto fields. There is no
upstream contract: the indices came from reading real responses, and Google
can change them without notice.

If you change an index, update the table in `README.md` in the same PR. That
table is the only documentation of the wire format, and a decoder that
disagrees with it is worse than no table at all.

## Scope

This package is data access plus aggregation that applies to any list.
Analysis that only makes sense for one particular group belongs in a script
that imports the package, not in the package.
