#!/usr/bin/env python3
"""
auto_sync.py — long-running watcher tied to REAL Codeforces acceptance.

It does NOT watch your local files for saves. It polls the Codeforces API
every SYNC_INTERVAL seconds and checks: "is there a problem with verdict OK
that I haven't committed yet?" Only when that's true does it:
  1. write the problem folder (pulling your code from solutions/ if present)
  2. git commit (one commit per newly-accepted problem)
  3. git push

If nothing new got accepted, it does nothing that cycle — no empty/fake commits.

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
from datetime import datetime, timezone
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


def git(*args, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(["git", *args], cwd=core.REPO_ROOT, env=env,
                             capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def commit_and_push(sub, prob_dir, has_code):
    key = core.problem_key(sub["problem"])
    name = sub["problem"].get("name", "?")
    ts = sub["creationTimeSeconds"]
    iso_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    rel_path = str(prob_dir.relative_to(core.REPO_ROOT))
    git("add", rel_path, "README.md")
    msg = f"Solve {key} - {name}" + (" [with code]" if has_code else "")
    res = git("commit", "-m", msg, env_extra={"GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date})
    if res.returncode != 0:
        return False
    push_res = git("push")
    return push_res.returncode == 0


def sync_once(done):
    subs = core.get_accepted_submissions(CF_HANDLE)
    new_subs = [s for s in subs if core.problem_key(s["problem"]) not in done]
    if not new_subs:
        return 0

    local_code = core.load_local_solutions()
    pushed = 0
    for s in new_subs:
        key = core.problem_key(s["problem"])
        tag_dir, folder, prob_dir = core.write_problem_folder(s, local_code)
        core.generate_readme(subs, local_code, CF_HANDLE)  # keep index in sync
        ok = commit_and_push(s, prob_dir, key in local_code)
        if ok:
            done.add(key)
            save_state(done)
            pushed += 1
            print(f"  ✅ pushed {key} - {s['problem'].get('name','?')}")
        else:
            print(f"  ⚠️  failed to push {key}, will retry next cycle")
    return pushed


def main():
    if not CF_HANDLE:
        raise SystemExit("Set CF_HANDLE env var to your Codeforces handle.")

    done = load_state()
    print(f"auto_sync.py running for {CF_HANDLE}, polling every {SYNC_INTERVAL}s. Ctrl+C to stop.")
    print(f"Already tracked: {len(done)} problems.\n")

    while True:
        try:
            now = datetime.now().strftime("%H:%M:%S")
            n = sync_once(done)
            if n:
                print(f"[{now}] {n} new problem(s) synced.")
            else:
                print(f"[{now}] no new AC submissions.")
        except Exception as e:
            print(f"[error] {e}")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
