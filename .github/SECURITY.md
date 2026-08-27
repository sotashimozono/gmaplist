# Security policy

## Reporting

Report a vulnerability through
[GitHub Security Advisories](https://github.com/sotashimozono/gmaplist/security/advisories/new).
Please do not open a public issue for a security report.

## Threat model

`gmaplist` handles no credentials. It performs unauthenticated `GET` requests
against `www.google.com` and `raw.githubusercontent.com`, and writes files to
paths the caller chooses. It has no runtime dependencies, so its supply chain
is the Python standard library plus the two hosts above.

## Handling the data it returns

This is the part that matters more than the code.

A shared list identifies real people. Every entry carries the display name and
the Google user id of whoever added it, and the notes are written by named
individuals. Exports produced by this tool are therefore personal data:

- Do not commit a share link, a list id, or an export to a public repository.
  A list id is a durable credential-like identifier: anyone holding it can
  read the whole list, including contributor names, without any further
  access.
- Treat `--csv`, `--json` and `--geojson` output as you would any other file
  containing other people's names.
- The test suite in this repository is deliberately offline and fixture-based
  for this reason. It contains no real list id and no real contributor.

## Scope

Reports about Google changing or removing the undocumented endpoint are
bugs, not vulnerabilities. Open a normal issue for those.
