"""
core.py — shared logic for CF Vault scripts (fetch.py, backfill.py, auto_sync.py)
"""

import os
import re
import requests
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

REPO_ROOT = Path(os.environ.get("REPO_ROOT", "."))
SOLUTIONS_DIR = REPO_ROOT / "solutions"
PROBLEMS_DIR = REPO_ROOT / "problems"

EXT_TO_LANG = {".cpp": "C++", ".py": "Python", ".java": "Java"}


def cf_get(method, params):
    r = requests.get(f"https://codeforces.com/api/{method}", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        raise RuntimeError(f"CF API error on {method}: {data.get('comment')}")
    return data["result"]


def sanitize(name):
    return re.sub(r"[^\w\-. ]", "", name).strip().replace(" ", "-")


def rating_bucket(rating):
    return f"{rating:04d}" if rating else "Unrated"


def primary_tag(tags):
    return sanitize(sorted(tags)[0]) if tags else "untagged"


def problem_key(prob):
    return f"{prob.get('contestId', 0)}{prob.get('index', '')}"


def get_accepted_submissions(handle):
    """One AC submission per problem (earliest), sorted oldest -> newest."""
    subs = cf_get("user.status", {"handle": handle, "from": 1, "count": 100000})
    best = {}
    for s in subs:
        if s.get("verdict") != "OK":
            continue
        key = problem_key(s["problem"])
        if key not in best or s["creationTimeSeconds"] < best[key]["creationTimeSeconds"]:
            best[key] = s
    return sorted(best.values(), key=lambda s: s["creationTimeSeconds"])


def load_local_solutions():
    SOLUTIONS_DIR.mkdir(exist_ok=True)
    found = {}
    for f in SOLUTIONS_DIR.iterdir():
        if f.suffix.lower() in EXT_TO_LANG:
            m = re.match(r"^(\d+[A-Za-z]\d*)", f.stem)
            if m:
                found[m.group(1)] = (EXT_TO_LANG[f.suffix.lower()], f.read_text(encoding="utf-8", errors="replace"))
    return found


def write_problem_folder(sub, local_code):
    prob = sub["problem"]
    cid, idx, name = prob.get("contestId", 0), prob.get("index", ""), prob.get("name", "Unknown")
    rating, tags = prob.get("rating"), prob.get("tags", [])
    key = problem_key(prob)

    tag_dir = primary_tag(tags)
    folder = f"{rating_bucket(rating)}_{key}-{sanitize(name)}"
    prob_dir = PROBLEMS_DIR / tag_dir / folder
    prob_dir.mkdir(parents=True, exist_ok=True)

    lang, code = local_code.get(key, (None, None))
    ext = next((e for e, l in EXT_TO_LANG.items() if l == lang), ".txt")

    readme = [
        f"# {key} — {name}",
        "",
        f"- **Contest:** [{cid}](https://codeforces.com/contest/{cid})",
        f"- **Rating:** {rating or 'Unrated'}",
        f"- **Tags:** {', '.join(f'`{t}`' for t in tags) or 'none'}",
        f"- **Submitted in:** {sub.get('programmingLanguage', '?')}",
        f"- **Submission:** [view](https://codeforces.com/contest/{cid}/submission/{sub['id']})",
        "",
    ]
    (prob_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")

    if code:
        (prob_dir / f"solution{ext}").write_text(code, encoding="utf-8")
    else:
        placeholder = prob_dir / "solution.todo"
        if not placeholder.exists():
            placeholder.write_text(
                f"Drop {key}.cpp / {key}.py / {key}.java into solutions/ and re-run to attach your code.\n",
                encoding="utf-8",
            )
    return tag_dir, folder, prob_dir


def build_streak_calendar(subs, weeks=12):
    by_day = defaultdict(int)
    for s in subs:
        d = datetime.utcfromtimestamp(s["creationTimeSeconds"]).date()
        by_day[d] += 1

    today = datetime.utcnow().date()
    start = today - timedelta(days=weeks * 7 - 1)
    chars = " ░▒▓█"
    row, day, streak, cur_streak = [], start, 0, 0
    while day <= today:
        c = by_day.get(day, 0)
        row.append(chars[min(c, 4)])
        if c > 0:
            cur_streak += 1
            streak = max(streak, cur_streak)
        else:
            cur_streak = 0
        day += timedelta(days=1)
    cur, day = 0, today
    while by_day.get(day, 0) > 0:
        cur += 1
        day -= timedelta(days=1)
    return "".join(row), streak, cur


def generate_readme(subs, local_code, handle):
    total = len(subs)
    with_code = sum(1 for s in subs if problem_key(s["problem"]) in local_code)

    tag_count, rating_count, lang_count = defaultdict(int), defaultdict(int), defaultdict(int)
    for s in subs:
        p = s["problem"]
        for t in p.get("tags", []):
            tag_count[t] += 1
        rating_count[rating_bucket(p.get("rating"))] += 1
        key = problem_key(p)
        lang = local_code.get(key, (s.get("programmingLanguage", "?"),))[0]
        lang_count[lang] += 1

    heat, longest, current = build_streak_calendar(subs)

    lines = [
        "# CF Vault", "",
        f"Auto-generated archive of accepted Codeforces submissions for **[{handle}](https://codeforces.com/profile/{handle})**.",
        "",
        f"- **Total solved:** {total}",
        f"- **With source attached:** {with_code} / {total}",
        f"- **Longest streak:** {longest} days  |  **Current streak:** {current} days",
        "", "## Activity (last 12 weeks)", "", "```", heat, "```", "",
        "## By language", "", "| Language | Solved |", "|---|---|",
    ]
    for lang, c in sorted(lang_count.items(), key=lambda x: -x[1]):
        lines.append(f"| {lang} | {c} |")

    lines += ["", "## By rating", "", "| Rating | Count |", "|---|---|"]
    for r, c in sorted(rating_count.items()):
        lines.append(f"| {r} | {c} |")

    lines += ["", "## By tag", "", "| Tag | Count |", "|---|---|"]
    for t, c in sorted(tag_count.items(), key=lambda x: -x[1]):
        lines.append(f"| `{t}` | {c} |")

    lines += ["", "## All problems", "", "| # | Problem | Rating | Tags | Code | Link |", "|---|---|---|---|---|---|"]
    for s in sorted(subs, key=lambda s: (s["problem"].get("rating") or 0, s["problem"].get("contestId", 0))):
        p = s["problem"]
        cid, idx, name = p.get("contestId", 0), p.get("index", ""), p.get("name", "?")
        key = problem_key(p)
        tag_dir = primary_tag(p.get("tags", []))
        folder = f"{rating_bucket(p.get('rating'))}_{key}-{sanitize(name)}"
        has_code = "✅" if key in local_code else "—"
        lines.append(
            f"| {key} | [{name}](problems/{tag_dir}/{folder}) | {p.get('rating') or '?'} | "
            f"{', '.join(f'`{t}`' for t in p.get('tags', []))} | {has_code} | "
            f"[CF](https://codeforces.com/contest/{cid}/problem/{idx}) |"
        )
    (REPO_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")
