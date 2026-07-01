# Setup — CF Vault

## 1. Push this as a new repo
```bash
cd cf-archive
git init
git add -A
git commit -m "init: cf vault scaffold"
git branch -M main
git remote add origin https://github.com/<your-username>/cf-vault.git
git push -u origin main
```

```bash
pip install -r requirements.txt
export CF_HANDLE=your_codeforces_handle
```

## 2. Backfill your ~60 already-solved problems (run ONCE)
```bash
python backfill.py
```
- Creates **one commit per already-solved problem**, dated to the problem's
  real Codeforces submission time (not today). This is honest history, not
  spam — each commit is a distinct, real solved problem.
- It'll ask for confirmation before making N commits.
- At the end, push everything: `git push -u origin main`
- Re-running it later is safe — it skips anything already committed
  (tracked in `.synced_problems.json`).

## 3. Auto-push every time you solve a new problem
```bash
python auto_sync.py
```
- Leave this running in a terminal/tmux while you do CP.
- It polls the Codeforces API every `SYNC_INTERVAL` seconds (default 120).
- It commits + pushes **only when a genuinely new AC submission appears**
  for your handle — not on a timer, not on file save. No new AC = no commit.
- Each commit is dated to the real submission timestamp and pushed
  immediately, so your GitHub graph fills in close to real-time.
- Stop anytime with Ctrl+C; it resumes cleanly next run.

Tune the poll interval if you want:
```bash
export SYNC_INTERVAL=60   # check every 60s instead of 120s
python auto_sync.py
```
Don't go below ~30s — it's pointless (you can't solve a new problem faster
than that) and just hammers the public CF API.

## 4. Attach your own code (recommended, anytime)
Before/after solving on Codeforces:
```bash
python new_problem.py 1850 A cpp     # scaffolds solutions/1850A.cpp
```
Solve it there. Next `fetch.py` / `auto_sync.py` run auto-attaches it into
`problems/<tag>/<rating>_<id>-<name>/solution.cpp`.

Manual naming convention if you drop files yourself into `solutions/`:
`<contestId><index>.<cpp|py|java>` e.g. `1850A.cpp`, `2103B.py`.

## 5. Full manual rebuild (optional)
```bash
python fetch.py
```
Rebuilds everything from scratch in one shot (no per-problem dated commits —
just use this if you want to force-refresh `problems/` + `README.md`).

## 6. Automate fully via GitHub Actions (optional, in addition to auto_sync.py)
1. Repo → **Settings → Secrets and variables → Actions → Variables**
2. Add `CF_HANDLE` = your handle
3. `.github/workflows/update.yml` runs daily as a safety-net full resync,
   and also re-runs when you push new files into `solutions/`.

## Folder structure
```
cf-vault/
├── core.py             # shared logic (used by all scripts below)
├── fetch.py             # full rebuild, one-shot
├── backfill.py            # ONE-TIME: dated commits for existing solves
├── auto_sync.py             # ONGOING: real-time commit+push on new AC
├── new_problem.py              # scaffold a file before you solve
├── templates/                    # cpp / py / java boilerplate
├── solutions/                       # you drop solved code here
├── problems/                           # AUTO-GENERATED
│   └── dp/1200_1850A-Problem-Name/
│       ├── README.md
│       └── solution.cpp
└── README.md                              # AUTO-GENERATED master index
```

## Notes
- Only the earliest AC per problem counts (no duplicate-solve spam).
- Don't hand-edit inside `problems/` — it's regenerated. Edit `solutions/`.
- CF's public API gives metadata only (name/rating/tags/link), not the
  actual problem statement text.
