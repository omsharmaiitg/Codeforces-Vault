# Codeforces Vault

Self-updating archive of my Codeforces solutions — organized by tag and
rating, with per-problem commits dated to when I actually solved them.

> This README is a placeholder. Run `fetch.py` (or `backfill.py` for the
> first sync) once Codeforces is reachable, and this file gets replaced
> with an auto-generated index: total solved, streak heatmap, tag/rating
> breakdowns, and a full problem table.

## What's in here

| File | Purpose |
|---|---|
| `core.py` | shared logic used by every script below |
| `fetch.py` | full rebuild — pulls all AC submissions, regenerates `problems/` + this README |
| `backfill.py` | one-time — creates one dated commit per already-solved problem |
| `auto_sync.py` | ongoing — polls CF, commits+pushes only on a genuinely new AC |
| `fetch_source.py` | pulls your actual submitted source code (needs a logged-in session cookie) |
| `new_problem.py` | scaffolds a solution file before you start solving |
| `templates/` | C++ / Python / Java boilerplate |
| `solutions/` | drop your solved code here, flat files named `<contestId><index>.<ext>` |
| `problems/` | auto-generated, organized `problems/<tag>/<rating>_<id>-<name>/` |

See `SETUP.md` for the full step-by-step.
