#!/usr/bin/env python3
"""
fetch_source.py — uses your own logged-in Codeforces browser session to
download the actual source code of your AC submissions into solutions/,
so backfill.py / auto_sync.py can attach real code instead of placeholders.

The public CF API only returns submission metadata (no source). Getting
your own code requires an authenticated session reading your submission
pages — same as this.

IMPORTANT: Codeforces added anti-bot protections (an AES-based "RCPC"
cookie challenge) that block plain scripted username/password logins —
even popular tools like cf-tool run into this. Rather than fight that
challenge, this script reuses YOUR OWN already-logged-in browser session,
which is the reliable, low-friction way to do this.

## How to get your session cookie (one-time, ~30 seconds):
1. Open codeforces.com in your browser and make sure you're logged in.
2. Press F12 (DevTools) -> Console tab.
3. Type:  document.cookie   and press Enter.
4. Copy the ENTIRE string it prints (long, semicolon-separated).
5. Run this script and paste it when prompted (or set env var
   CF_SESSION_COOKIE beforehand to skip the prompt).

Cookies expire after a while — if the script suddenly starts failing,
just repeat the steps above to get a fresh cookie string.

Usage:
    python fetch_source.py
"""

import os
import re
import sys
import time
import html
import requests
import core

BASE = "https://codeforces.com"
LANG_EXT = [
    ("python", ".py"),
    ("pypy", ".py"),
    ("c++", ".cpp"),
    ("gnu c", ".cpp"),
    ("java", ".java"),
]


def guess_ext(lang):
    lang_l = lang.lower()
    for needle, ext in LANG_EXT:
        if needle in lang_l:
            return ext
    return None


def session_from_cookie_string(cookie_string):
    """Parse a raw `document.cookie` string ('a=1; b=2; ...') into a session."""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (cf-vault fetch_source.py)"})
    for part in cookie_string.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            session.cookies.set(k.strip(), v.strip(), domain="codeforces.com")
    return session


def check_logged_in(session, handle):
    r = session.get(f"{BASE}/profile/{handle}", timeout=30)
    if handle.lower() not in r.text.lower() or "/enter?" in r.url:
        raise RuntimeError(
            "Doesn't look logged in with that cookie. Re-copy document.cookie "
            "fresh from your browser (make sure you're logged in there) and try again."
        )
    print("Session looks valid.")


def fetch_source(session, contest_id, submission_id):
    urls = [
        f"{BASE}/contest/{contest_id}/submission/{submission_id}",
        f"{BASE}/problemset/submission/{contest_id}/{submission_id}",
    ]
    for url in urls:
        r = session.get(url, timeout=30)
        m = re.search(r'<pre[^>]*id="program-source-text"[^>]*>(.*?)</pre>', r.text, re.DOTALL)
        if m:
            raw = re.sub(r"<[^>]+>", "", m.group(1))  # strip stray tags (line-number spans) BEFORE unescaping
            code = html.unescape(raw)                  # so escaped entities like &lt;bits/stdc++.h&gt; survive intact
            return code
    return None


def main():
    handle = os.environ.get("CF_HANDLE", "").strip() or input("Codeforces handle: ").strip()

    cookie_string = os.environ.get("CF_SESSION_COOKIE", "").strip()
    if not cookie_string:
        print("\nPaste your browser's document.cookie value (see instructions at the top of this file).")
        cookie_string = input("Cookie string: ").strip()

    session = session_from_cookie_string(cookie_string)
    try:
        check_logged_in(session, handle)
    except Exception as e:
        print(f"\n{e}")
        sys.exit(1)

    print(f"Fetching AC submission list for {handle}...")
    subs = core.get_accepted_submissions(handle)
    existing = core.load_local_solutions()
    print(f"{len(subs)} solved problems, {len(existing)} already have local code.")

    core.SOLUTIONS_DIR.mkdir(exist_ok=True)
    fetched, skipped, failed = 0, 0, 0

    for i, s in enumerate(subs, 1):
        key = core.problem_key(s["problem"])
        if key in existing:
            skipped += 1
            continue

        ext = guess_ext(s.get("programmingLanguage", ""))
        if not ext:
            print(f"  [{i}/{len(subs)}] {key}: unsupported language ({s.get('programmingLanguage')}), skipping")
            skipped += 1
            continue

        try:
            code = fetch_source(session, s["problem"].get("contestId"), s["id"])
        except Exception as e:
            print(f"  [{i}/{len(subs)}] {key}: request failed ({e})")
            failed += 1
            time.sleep(1)
            continue

        if not code:
            print(f"  [{i}/{len(subs)}] {key}: source not found on page (private or removed?)")
            failed += 1
            time.sleep(1)
            continue

        out_path = core.SOLUTIONS_DIR / f"{key}{ext}"
        out_path.write_text(code, encoding="utf-8")
        fetched += 1
        print(f"  [{i}/{len(subs)}] {key}: saved -> {out_path.name}")
        time.sleep(1)  # be polite to CF's servers

    print(f"\nDone. Fetched {fetched}, already had {skipped}, failed {failed}.")
    print("Now run backfill.py (or fetch.py) to attach this code into problems/.")


if __name__ == "__main__":
    main()
