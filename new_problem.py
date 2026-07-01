#!/usr/bin/env python3
"""
new_problem.py — scaffold a solution file before you start solving.

Usage:
    python new_problem.py 1850 A cpp
    python new_problem.py 1850 A py
    python new_problem.py 1850 A java

Fetches the problem's name/rating/tags from the public CF problemset API
(no auth needed) and drops a pre-filled solutions/<id>.<ext> file from the
matching template. Solve it there, then run fetch.py to archive it.
"""

import sys
import requests
from pathlib import Path

SOLUTIONS_DIR = Path("solutions")
TEMPLATES_DIR = Path("templates")
EXT_MAP = {"cpp": ".cpp", "py": ".py", "java": ".java"}


def find_problem(contest_id, index):
    r = requests.get("https://codeforces.com/api/problemset.problems", timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        raise RuntimeError(data.get("comment"))
    for p in data["result"]["problems"]:
        if str(p.get("contestId")) == str(contest_id) and p.get("index") == index:
            return p
    return None


def main():
    if len(sys.argv) != 4:
        print("Usage: python new_problem.py <contestId> <index> <cpp|py|java>")
        sys.exit(1)

    contest_id, index, lang = sys.argv[1], sys.argv[2].upper(), sys.argv[3].lower()
    if lang not in EXT_MAP:
        print(f"Unknown language '{lang}'. Choose from: {list(EXT_MAP)}")
        sys.exit(1)

    print(f"Looking up {contest_id}{index}...")
    prob = find_problem(contest_id, index)
    if not prob:
        print("Problem not found in CF problemset API (might be a gym/unrated contest).")
        prob = {"name": "Unknown", "rating": None, "tags": []}

    SOLUTIONS_DIR.mkdir(exist_ok=True)
    ext = EXT_MAP[lang]
    out_path = SOLUTIONS_DIR / f"{contest_id}{index}{ext}"
    if out_path.exists():
        print(f"{out_path} already exists, not overwriting.")
        sys.exit(0)

    template_path = TEMPLATES_DIR / f"template{ext}"
    body = template_path.read_text(encoding="utf-8") if template_path.exists() else ""

    header = (
        f"// {contest_id}{index} - {prob.get('name', '?')}\n"
        f"// Rating: {prob.get('rating', '?')}  Tags: {', '.join(prob.get('tags', []))}\n"
        f"// https://codeforces.com/contest/{contest_id}/problem/{index}\n\n"
    )
    if lang == "py":
        header = header.replace("//", "#")

    out_path.write_text(header + body, encoding="utf-8")
    print(f"Created {out_path}. Happy solving!")


if __name__ == "__main__":
    main()
