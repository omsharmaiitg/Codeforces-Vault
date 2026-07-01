#!/usr/bin/env python3
"""
auto_sync.py — long-running watcher tied to REAL Codeforces acceptance
AND rating changes.

It does NOT watch your local files for saves. It polls the Codeforces API
every SYNC_INTERVAL seconds and, every cycle:
  1. checks for newly-accepted problems (writes their folders)
  2. ALWAYS regenerates README.md + all analytics charts (rating history,
     activity heatmap, etc.) — this matters even when zero new problems
     were solved, e.g. after a contest that only changed your rating.
  3. stages everything, and commits+pushes ONLY IF something actually
     changed on disk (git commit is a no-op otherwise) — so idle cycles
     never create empty/fake commits.

Usage:
    export CF_HANDLE=your_handle
    export SYNC_INTERVAL=120        # seconds between polls, default 120
    python auto_sync.py

Leave this running in a terminal (or tmux/screen) while you grind problems.
Tip: don't set SYNC_INTERVAL below ~30s — Codeforces rate-limits the public
API, and there's no benefit since nothing changes faster than you can solve.
"""

import os
import json
import time
import subprocess
from datetime import datetime
import core

CF_HANDLE = os.environ.get("CF_HANDLE", "").strip()
SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", "120"))
STATE_FILE = core.REPO_ROOT / ".synced_problems.json"


def load_state():
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_state(done):
    STATE_FILE.write_text(json.dumps(sorted(done)), encoding="utf-8")


def git(*args):
    result = subprocess.run(["git", *args], cwd=core.REPO_ROOT,
                             capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def sync_once(done):
    """Returns (new_problem_count, committed: bool)."""
    subs = core.get_accepted_submissions(CF_HANDLE)
    new_subs = [s for s in subs if core.problem_key(s["problem"]) not in done]
    local_code = core.load_local_solutions()

    for s in new_subs:
        core.write_problem_folder(s, local_code)
        done.add(core.problem_key(s["problem"]))

    # Always regenerate — this is what picks up rating changes, streak
    # updates, and chart refreshes even when no new problem was solved.
    core.generate_readme(subs, local_code, CF_HANDLE)
    save_state(done)

    git("add", "problems", "README.md", "assets", str(STATE_FILE.name))
    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=core.REPO_ROOT)
    if diff_check.returncode == 0:
        return len(new_subs), False  # nothing actually changed, no-op

    if new_subs:
        names = ", ".join(core.problem_key(s["problem"]) for s in new_subs[:5])
        suffix = f" (+{len(new_subs) - 5} more)" if len(new_subs) > 5 else ""
        msg = f"Sync: {len(new_subs)} new problem(s) — {names}{suffix}"
    else:
        msg = "Sync: refresh analytics (rating/streak update, no new problems)"

    commit_res = git("commit", "-m", msg)
    if commit_res.returncode != 0:
        return len(new_subs), False

    push_res = git("push")
    return len(new_subs), push_res.returncode == 0


def main():
    if not CF_HANDLE:
        raise SystemExit("Set CF_HANDLE env var to your Codeforces handle.")

    run_once = os.environ.get("RUN_ONCE", "").strip().lower() in ("1", "true", "yes")

    done = load_state()
    print(f"auto_sync.py running for {CF_HANDLE}" + (" (single run mode)." if run_once else f", polling every {SYNC_INTERVAL}s. Ctrl+C to stop."))
    print(f"Already tracked: {len(done)} problems.\n")

    def cycle():
        now = datetime.now().strftime("%H:%M:%S")
        try:
            n_new, committed = sync_once(done)
            if committed and n_new:
                print(f"[{now}] pushed {n_new} new problem(s) + refreshed analytics.")
            elif committed:
                print(f"[{now}] refreshed analytics (rating/streak change detected), pushed.")
            else:
                print(f"[{now}] no changes to sync.")
        except Exception as e:
            print(f"[{now}] [error] {e}")

    if run_once:
        cycle()
        return

    while True:
        cycle()
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
