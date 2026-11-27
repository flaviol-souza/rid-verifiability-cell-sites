# Private working repository

Working repository for the paper *Hearing Is Not Verifying* (SBRC 2027). It holds code, tests and private tooling.
The public repository, `rid-verifiability-cell-sites`, is built from this one:

```bash
python tools/export_public.py --manifest tools/MANIFEST-PUBLIC.txt --dest ../rid-verifiability-cell-sites --dry-run
```

The public README is `public/README.md`. Raw data, `data/`, `docs/`, `.kiro/`, `CLAUDE.md`, `AGENTS.md` and `notes.md` stay local and are git-ignored.
Never publish anything outside the allowlist in `tools/MANIFEST-PUBLIC.txt`.

Tests: `python -m pytest -q`