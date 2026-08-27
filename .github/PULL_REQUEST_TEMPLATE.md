## What changed

<!-- One paragraph. What behaviour is different after this PR? -->

## Why

<!-- The problem being solved. Link an issue with "Refs #N", or "Closes #N"
     only if this PR actually fixes it and the issue is yours. -->

## Checklist

- [ ] `version` in `pyproject.toml` is bumped (the `version-check` job is a
      required check and will fail otherwise)
- [ ] `python -m unittest discover -s tests` passes
- [ ] `ruff check . && ruff format --check .` passes
      (`pip install -r requirements-dev.txt` for the pinned version)
- [ ] No share link, list id, contributor name, or real export is included
      anywhere in the diff — see `.github/SECURITY.md`
- [ ] If a payload index in `gmaplist/model.py` changed, the index table in
      `README.md` is updated to match
