#!/usr/bin/env python3
"""
fetch.py — full rebuild: pulls all AC submissions, regenerates problems/ + README.md.
Run this anytime for a complete resync. For incremental, real-time commits
(one per newly solved problem), use auto_sync.py instead.
"""
import os
import time
import json
from pathlib import Path
import core

CF_HANDLE = os.environ.get("CF_HANDLE", "").strip()
CACHE_FILE = core.REPO_ROOT / ".cf_cache.json"


def main():
    if not CF_HANDLE:
        raise SystemExit("Set CF_HANDLE env var to your Codeforces handle.")

    print(f"Fetching AC submissions for {CF_HANDLE}...")
    subs = core.get_accepted_submissions(CF_HANDLE)
    print(f"Found {len(subs)} unique solved problems.")

    local_code = core.load_local_solutions()
    print(f"Found {len(local_code)} local solution files in solutions/.")

    for i, s in enumerate(subs, 1):
        tag_dir, folder, _ = core.write_problem_folder(s, local_code)
        key = core.problem_key(s["problem"])
        tag = " [code]" if key in local_code else ""
        print(f"  [{i}/{len(subs)}] {key}{tag} -> problems/{tag_dir}/{folder}")

    core.generate_readme(subs, local_code, CF_HANDLE)
    CACHE_FILE.write_text(json.dumps({"updated": int(time.time()), "count": len(subs)}), encoding="utf-8")
    print("\nDone. README.md regenerated.")


if __name__ == "__main__":
    main()
