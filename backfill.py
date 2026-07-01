#!/usr/bin/env python3
"""
backfill.py — one-time setup script.

Walks through ALL your already-solved problems (oldest to newest) and makes
ONE git commit per problem, with the commit's author/commit date set to the
problem's REAL Codeforces submission date — not today's date. This makes
your repo history honestly reflect when you actually solved each problem,
instead of one giant "initial import" commit.

This is NOT the same as spam-committing the same data repeatedly — each
commit here corresponds to one real, distinct solved problem, dated truthfully.

Run this ONCE after creating the repo. For ongoing problems you solve from
now on, use auto_sync.py instead (it commits each new AC submission in
near-real-time, also with its true date).

Usage:
    export CF_HANDLE=your_handle
    python backfill.py
"""

import os
import subprocess
from datetime import datetime, timezone
import core

CF_HANDLE = os.environ.get("CF_HANDLE", "").strip()
STATE_FILE = core.REPO_ROOT / ".synced_problems.json"


def already_committed():
    import json
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def mark_committed(key):
    import json
    done = already_committed()
    done.add(key)
    STATE_FILE.write_text(json.dumps(sorted(done)), encoding="utf-8")


def git(*args, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(["git", *args], cwd=core.REPO_ROOT, env=env,
                             capture_output=True, text=True)
    if result.returncode != 0:
        print(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result


def commit_for_submission(sub, prob_dir, local_code_present):
    key = core.problem_key(sub["problem"])
    name = sub["problem"].get("name", "?")
    ts = sub["creationTimeSeconds"]
    iso_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    rel_path = str(prob_dir.relative_to(core.REPO_ROOT))
    git("add", rel_path)

    msg = f"Solve {key} - {name}"
    if local_code_present:
        msg += " [with code]"

    env_extra = {"GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date}
    res = git("commit", "-m", msg, env_extra=env_extra)
    return res.returncode == 0


def main():
    if not CF_HANDLE:
        raise SystemExit("Set CF_HANDLE env var to your Codeforces handle.")

    print(f"Fetching AC submissions for {CF_HANDLE} (oldest first)...")
    subs = core.get_accepted_submissions(CF_HANDLE)  # already sorted oldest -> newest
    local_code = core.load_local_solutions()
    done = already_committed()

    todo = [s for s in subs if core.problem_key(s["problem"]) not in done]
    print(f"{len(subs)} total solved, {len(done)} already backfilled, {len(todo)} to commit now.\n")

    if not todo:
        print("Nothing new to backfill.")
        return

    confirm = input(f"This will create {len(todo)} separate dated commits. Continue? [y/N] ")
    if confirm.strip().lower() != "y":
        print("Aborted.")
        return

    committed = 0
    for i, s in enumerate(todo, 1):
        key = core.problem_key(s["problem"])
        tag_dir, folder, prob_dir = core.write_problem_folder(s, local_code)
        ok = commit_for_submission(s, prob_dir, key in local_code)
        if ok:
            mark_committed(key)
            committed += 1
            print(f"  [{i}/{len(todo)}] committed {key} ({s['problem'].get('name','?')})")
        else:
            print(f"  [{i}/{len(todo)}] skipped {key} (no changes or git error)")

    # one final commit to rebuild the master README/index, dated now
    core.generate_readme(subs, local_code, CF_HANDLE)
    git("add", "README.md")
    git("commit", "-m", "chore: rebuild master index")

    print(f"\nDone. {committed} dated commits created.")
    print("Now push them: git push -u origin main")


if __name__ == "__main__":
    main()
