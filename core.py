"""
core.py — shared logic for CF Vault scripts (fetch.py, backfill.py, auto_sync.py)
"""

import os
import re
import requests
import matplotlib
matplotlib.use("Agg")  # no display needed, works in CI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta, timezone

REPO_ROOT = Path(os.environ.get("REPO_ROOT", "."))
SOLUTIONS_DIR = REPO_ROOT / "solutions"
PROBLEMS_DIR = REPO_ROOT / "problems"
ASSETS_DIR = REPO_ROOT / "assets" / "charts"

EXT_TO_LANG = {".cpp": "C++", ".py": "Python", ".java": "Java"}

# Day-bucketing for streak/heatmap uses this timezone, not UTC — otherwise
# submissions made late at night (IST) get counted on the wrong calendar
# day and streaks come out shorter than what your CF profile shows you
# (CF's own activity page buckets by your local browser timezone).
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))  # IST

# ---- shared chart look & feel -------------------------------------------------
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#444444",
    "axes.labelcolor": "#222222",
    "text.color": "#222222",
    "xtick.color": "#444444",
    "ytick.color": "#444444",
    "font.size": 10,
    "axes.grid": True,
    "grid.color": "#e6e6e6",
    "grid.linewidth": 0.6,
})
ACCENT = "#2f81f7"      # GitHub-blue-ish accent
ACCENT2 = "#3fb950"     # green accent
PALETTE = ["#2f81f7", "#3fb950", "#f0883e", "#a371f7", "#f85149", "#db61a2", "#56d364"]


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


def get_all_ac_timestamps(handle):
    """Every accepted submission's timestamp (NOT deduped per problem).
    Used for streak/activity — resubmitting or re-solving an already-AC'd
    problem still counts as activity that day, matching how CF's own
    streak counters work."""
    subs = cf_get("user.status", {"handle": handle, "from": 1, "count": 100000})
    return [s["creationTimeSeconds"] for s in subs if s.get("verdict") == "OK"]


def get_rating_history(handle):
    """List of contest rating changes, oldest first. Empty list if user has never rated."""
    try:
        return cf_get("user.rating", {"handle": handle})
    except RuntimeError:
        return []


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


def normalize_lang(raw_lang):
    lang_l = (raw_lang or "Other").lower()
    if "c++" in lang_l or "gnu c" in lang_l:
        return "C++"
    if "python" in lang_l or "pypy" in lang_l:
        return "Python"
    if "java" in lang_l:
        return "Java"
    return raw_lang or "Other"


def chart_rating_history(history):
    """Line chart of contest rating over time, CF-profile style."""
    if not history:
        return None

    dates = [datetime.utcfromtimestamp(h["ratingUpdateTimeSeconds"]) for h in history]
    ratings = [h["newRating"] for h in history]

    # CF-style rank tier color bands (rough thresholds)
    bands = [
        (0, 1200, "#cccccc"), (1200, 1400, "#77ff77"), (1400, 1600, "#77ddbb"),
        (1600, 1900, "#aaaaff"), (1900, 2100, "#ff88ff"), (2100, 2300, "#ffcc88"),
        (2300, 2400, "#ffbb55"), (2400, 2600, "#ff7777"), (2600, 3000, "#ff3333"),
        (3000, 4000, "#aa0000"),
    ]

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for lo, hi, color in bands:
        ax.axhspan(lo, hi, color=color, alpha=0.25, zorder=0)

    ax.plot(dates, ratings, color="#222222", linewidth=1.5, zorder=2)
    ax.scatter(dates, ratings, color="#222222", s=18, zorder=3)

    ymin = min(ratings) - 100
    ymax = max(ratings) + 100
    ax.set_ylim(max(0, ymin), ymax)
    ax.set_title(f"Rating History — current {ratings[-1]}, max {max(ratings)}",
                 fontsize=13, fontweight="bold", loc="left")
    ax.set_ylabel("Rating")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()
    return _save(fig, "rating_history.png")


def chart_problem_type_distribution(subs):
    """Pie chart of solved problems grouped by contest position letter (A, B, C...)."""
    type_count = defaultdict(int)
    for s in subs:
        idx = s["problem"].get("index", "?")
        letter = idx[0].upper() if idx else "?"
        type_count[letter] += 1

    letters = sorted(type_count.keys())
    counts = [type_count[l] for l in letters]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(letters))]

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, _ = ax.pie(
        counts, colors=colors, startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.5},
    )
    ax.set_title("Solved by Problem Type (position)", fontsize=13, fontweight="bold", loc="left")
    legend_labels = [f"{l} : {c}" for l, c in zip(letters, counts)]
    ax.legend(
        wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
        fontsize=9, frameon=False, handlelength=1.2, handleheight=1.2,
    )
    return _save(fig, "problem_type_distribution.png")


def _save(fig, name):
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSETS_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_rating_distribution(subs):
    buckets = defaultdict(int)
    for s in subs:
        r = s["problem"].get("rating")
        buckets[r if r else 0] += 1
    xs = sorted(buckets.keys())
    labels = [("Unrated" if x == 0 else str(x)) for x in xs]
    ys = [buckets[x] for x in xs]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(labels, ys, color=ACCENT, width=0.7)
    ax.set_title("Problems Solved by Rating", fontsize=13, fontweight="bold")
    ax.set_xlabel("Rating")
    ax.set_ylabel("Problems solved")
    ax.tick_params(axis="x", rotation=60)
    for i, y in enumerate(ys):
        ax.text(i, y + max(ys) * 0.01, str(y), ha="center", fontsize=8)
    return _save(fig, "rating_distribution.png")


def chart_tag_distribution(subs, top_n=15):
    tag_count = defaultdict(int)
    for s in subs:
        for t in s["problem"].get("tags", []):
            tag_count[t] += 1
    top = sorted(tag_count.items(), key=lambda x: -x[1])[:top_n]
    tags = [t[0] for t in top]
    counts = [t[1] for t in top]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(tags))]

    fig, ax = plt.subplots(figsize=(8, 5))
    wedges, _ = ax.pie(
        counts, colors=colors, startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.5},
    )
    ax.set_title("Tags Solved", fontsize=13, fontweight="bold", loc="left")
    legend_labels = [f"{t} : {c}" for t, c in zip(tags, counts)]
    ax.legend(
        wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
        fontsize=9, frameon=False, handlelength=1.2, handleheight=1.2,
    )
    return _save(fig, "tag_distribution.png")


def chart_cumulative_progress(subs):
    dates = sorted(datetime.utcfromtimestamp(s["creationTimeSeconds"]).date() for s in subs)
    if not dates:
        return None
    cum_x, cum_y = [], []
    count = 0
    for d in dates:
        count += 1
        cum_x.append(d)
        cum_y.append(count)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(cum_x, cum_y, color=ACCENT, linewidth=2)
    ax.fill_between(cum_x, cum_y, color=ACCENT, alpha=0.12)
    ax.set_title("Cumulative Problems Solved Over Time", fontsize=13, fontweight="bold")
    ax.set_ylabel("Total solved")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()
    return _save(fig, "cumulative_progress.png")


def chart_language_breakdown(subs, local_code):
    lang_count = defaultdict(int)
    for s in subs:
        key = problem_key(s["problem"])
        raw_lang = local_code.get(key, (s.get("programmingLanguage", "Other"),))[0]
        lang_count[normalize_lang(raw_lang)] += 1

    labels = list(lang_count.keys())
    sizes = list(lang_count.values())
    colors = PALETTE[: len(labels)]

    fig, ax = plt.subplots(figsize=(5, 5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.0f%%", colors=colors,
        startangle=90, textprops={"fontsize": 10}
    )
    ax.set_title("Solved by Language", fontsize=13, fontweight="bold")
    return _save(fig, "language_breakdown.png")


def chart_activity_heatmap(timestamps, weeks=52):
    """GitHub-style contribution calendar for the last `weeks` weeks."""
    by_day = defaultdict(int)
    for ts in timestamps:
        d = datetime.fromtimestamp(ts, tz=LOCAL_TZ).date()
        by_day[d] += 1

    today = datetime.now(tz=LOCAL_TZ).date()
    # align start to the most recent Sunday on/before (today - weeks*7)
    start = today - timedelta(days=weeks * 7 - 1)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # back up to Sunday

    n_days = (today - start).days + 1
    n_weeks = n_days // 7 + 1
    grid = [[None] * n_weeks for _ in range(7)]  # 7 rows (Sun..Sat), n_weeks cols

    day = start
    while day <= today:
        w = (day - start).days // 7
        dow = (day.weekday() + 1) % 7  # convert Mon=0..Sun=6 -> Sun=0..Sat=6
        grid[dow][w] = by_day.get(day, 0)
        day += timedelta(days=1)

    max_count = max((c for row in grid for c in row if c is not None), default=1) or 1

    fig, ax = plt.subplots(figsize=(max(8, n_weeks * 0.22), 2.4))
    for dow in range(7):
        for w in range(n_weeks):
            c = grid[dow][w]
            if c is None:
                continue
            intensity = 0 if c == 0 else min(1.0, 0.25 + 0.75 * (c / max_count))
            color = "#ebedf0" if c == 0 else plt.cm.Greens(intensity)
            ax.add_patch(plt.Rectangle((w, 6 - dow), 0.85, 0.85, color=color))

    ax.set_xlim(-0.5, n_weeks + 0.5)
    ax.set_ylim(-0.5, 7.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Activity — last {weeks} weeks", fontsize=13, fontweight="bold", loc="left")
    return _save(fig, "activity_heatmap.png")


def generate_all_charts(subs, local_code, rating_history=None, all_ac_timestamps=None):
    """Generates every chart, tolerating individual failures so one bad
    chart doesn't block README generation."""
    made = {}
    heatmap_source = all_ac_timestamps if all_ac_timestamps is not None else [s["creationTimeSeconds"] for s in subs]
    chart_list = [
        ("rating_distribution.png", chart_rating_distribution, (subs,)),
        ("tag_distribution.png", chart_tag_distribution, (subs,)),
        ("cumulative_progress.png", chart_cumulative_progress, (subs,)),
        ("language_breakdown.png", chart_language_breakdown, (subs, local_code)),
        ("problem_type_distribution.png", chart_problem_type_distribution, (subs,)),
        ("activity_heatmap.png", chart_activity_heatmap, (heatmap_source,)),
    ]
    if rating_history:
        chart_list.append(("rating_history.png", chart_rating_history, (rating_history,)))
    for name, fn, args in chart_list:
        try:
            fn(*args)
            made[name] = True
        except Exception as e:
            print(f"  [charts] skipped {name}: {e}")
            made[name] = False
    return made


def build_streak_calendar(timestamps, weeks=12):
    by_day = defaultdict(int)
    for ts in timestamps:
        d = datetime.fromtimestamp(ts, tz=LOCAL_TZ).date()
        by_day[d] += 1

    today = datetime.now(tz=LOCAL_TZ).date()
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
        raw_lang = local_code.get(key, (s.get("programmingLanguage", "Other"),))[0]
        lang_count[normalize_lang(raw_lang)] += 1

    all_ac_timestamps = get_all_ac_timestamps(handle)
    heat, longest, current = build_streak_calendar(all_ac_timestamps)
    rating_history = get_rating_history(handle)
    chart_status = generate_all_charts(subs, local_code, rating_history, all_ac_timestamps)

    lines = [
        "# CF Vault", "",
        f"Auto-generated archive of accepted Codeforces submissions for **[{handle}](https://codeforces.com/profile/{handle})**.",
        "",
        f"- **Total solved:** {total}",
        f"- **With source attached:** {with_code} / {total}",
        f"- **Longest streak:** {longest} days  |  **Current streak:** {current} days",
    ]
    if rating_history:
        lines.append(f"- **Contest rating:** {rating_history[-1]['newRating']} (max {max(h['newRating'] for h in rating_history)})")
    lines.append("")

    lines.append("## 📊 Analytics")
    lines.append("")

    chart_order = [
        "rating_history.png",
        "activity_heatmap.png",
        "cumulative_progress.png",
        "rating_distribution.png",
        "tag_distribution.png",
        "language_breakdown.png",
        "problem_type_distribution.png",
    ]
    for chart_file in chart_order:
        if chart_status.get(chart_file):
            lines += [f'<img src="assets/charts/{chart_file}" width="100%" />', ""]

    if not any(chart_status.values()):
        lines += ["_(charts unavailable this run — text summary below)_", "", "```", heat, "```", ""]

    lines += ["<details>", "<summary>📋 Raw tables (language / rating / tag breakdown)</summary>", ""]

    lines += ["", "### By language", "", "| Language | Solved |", "|---|---|"]
    for lang, c in sorted(lang_count.items(), key=lambda x: -x[1]):
        lines.append(f"| {lang} | {c} |")

    lines += ["", "### By rating", "", "| Rating | Count |", "|---|---|"]
    for r, c in sorted(rating_count.items()):
        lines.append(f"| {r} | {c} |")

    lines += ["", "### By tag", "", "| Tag | Count |", "|---|---|"]
    for t, c in sorted(tag_count.items(), key=lambda x: -x[1]):
        lines.append(f"| `{t}` | {c} |")

    lines += ["", "</details>", ""]

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
