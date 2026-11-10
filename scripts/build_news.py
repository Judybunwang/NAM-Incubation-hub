"""Build news/latest.json for the "Food-tech news" tab from a Food-Tech Scout checkout.

Usage: python scripts/build_news.py PATH_TO_PURATOSSCOUTING

1. Archive: for every day the scout has scored, it saves that day's candidate items
   (relevance 5+) plus Claude's daily headline and summary to news/archive/<day>.json.
   The archive lives in this repo, so history keeps growing after the scout's own
   retention window ends.
2. Roll-up: it groups the archive into periods for the tab's dropdown:
     - weekly   the last 5 weeks (Monday to Sunday), including the week in progress
     - monthly  every completed month (last 12)
     - quarterly every completed quarter (Q1-Q4)
   Each period lists its top items (de-duplicated across days, ranked by relevance)
   and its regulatory items.
3. Summary: a period's headline and executive summary come from
   news/summaries/<period id>.json when it exists (written by a weekly Claude task, see
   news/summaries/README.md). Otherwise a simple summary is built from the top items.

Standard library only, so the GitHub Action needs no installs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "news"
ARCHIVE = NEWS / "archive"
SUMMARIES = NEWS / "summaries"
OUT = NEWS / "latest.json"

WEEKS_SHOWN = 5
MONTHS_SHOWN = 12
TOP = {"week": (12, 4), "month": (18, 6), "quarter": (24, 8)}  # (items, regulatory)
CANDIDATE_MIN = 5


def safe_url(u: str) -> str:
    u = (u or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def slim(it: dict) -> dict:
    return {
        "id": it.get("id", ""),
        "title": it.get("title", ""),
        "url": safe_url(it.get("url", "")),
        "source": it.get("source", "").replace("Google News: ", ""),
        "kind": it.get("kind", ""),
        "published": it.get("published", ""),
        "day": it.get("first_seen", ""),
        "unit": it.get("primary_bu", ""),
        "scores": {k: round(v) for k, v in (it.get("bu_scores") or {}).items()},
        "relevance": round(it.get("relevance", 0), 1),
        "horizon": it.get("horizon", ""),
        "category": it.get("category", ""),
        "region": it.get("region", ""),
        "summary": it.get("ai_summary") or "",
        "why": it.get("why_it_matters") or "",
        "image": safe_url(it.get("image", "")),
        "entities": (it.get("entities") or [])[:6],
    }


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_if_changed(path: Path, obj) -> bool:
    text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if path.exists() and path.read_text() == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return True


# ---------- 1. archive ----------

def archive_from_scout(scout: Path) -> int:
    items = read_json(scout / "data" / "items.json", [])
    by_day: dict[str, list[dict]] = {}
    for it in items:
        by_day.setdefault(it.get("first_seen", ""), []).append(it)
    changed = 0
    for p in sorted((scout / "data" / "claude").glob("*.json")):
        day = p.stem
        todays = by_day.get(day, [])
        if not todays:
            continue
        notes = read_json(p, {})
        notes = notes if isinstance(notes, dict) else {}
        keep = sorted((i for i in todays if i.get("relevance", 0) >= (CANDIDATE_MIN if i.get("kind") == "regulation" else 6)),
                      key=lambda i: (i.get("relevance", 0), i.get("prefilter", 0)), reverse=True)
        changed += write_if_changed(ARCHIVE / f"{day}.json", {
            "date": day,
            "headline": str(notes.get("headline", "")).strip(),
            "summary": [str(s) for s in (notes.get("executive_summary") or [])][:5],
            "scanned": len(todays),
            "items": [slim(i) for i in keep],
        })
    return changed


# ---------- 2. periods ----------

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def quarter_of(d: date) -> int:
    return (d.month - 1) // 3 + 1


def month_end(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)


def fmt_range(a: date, b: date) -> str:
    if a.month == b.month:
        return f"{a:%b} {a.day} – {b.day}, {b.year}"
    if a.year == b.year:
        return f"{a:%b} {a.day} – {b:%b} {b.day}, {b.year}"
    return f"{a:%b} {a.day}, {a.year} – {b:%b} {b.day}, {b.year}"


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def story_keys(it: dict) -> set[str]:
    """Keys that mark two articles as the same story: same title, same why-it-matters
    line, or same lead organisation in the same category."""
    keys = {"t:" + norm(it["title"])}
    if it["why"]:
        keys.add("w:" + norm(it["why"]))
    if it["entities"]:
        keys.add("e:" + norm(it["entities"][0]) + "|" + it["category"])
    return keys


def roll_up(days: list[dict], kind: str) -> tuple[list[dict], list[dict]]:
    allitems = [it for d in days for it in d["items"]]
    allitems.sort(key=lambda i: (i["relevance"], bool(i["image"]), i["day"]), reverse=True)
    stories: list[dict] = []
    seen: dict[str, dict] = {}
    for it in allitems:
        hit = next((seen[k] for k in story_keys(it) if k in seen), None)
        if hit:
            hit["coverage"] += 1
            if not hit["image"] and it["image"]:
                hit["image"] = it["image"]
        else:
            hit = dict(it, coverage=1)
            stories.append(hit)
        for k in story_keys(it):
            seen.setdefault(k, hit)
    ranked = sorted(stories, key=lambda i: (i["relevance"], i["coverage"]), reverse=True)
    n_items, n_regs = TOP[kind]
    news = [i for i in ranked if i["kind"] != "regulation" and i["relevance"] >= 6][:n_items]
    regs = [i for i in ranked if i["kind"] == "regulation" and i["relevance"] >= 5][:n_regs]
    return news, regs


def fallback_summary(news: list[dict], regs: list[dict]) -> tuple[str, list[str]]:
    top = news[:4] + regs[:1]
    headline = "; ".join(i["title"] for i in news[:2])
    return headline[:110], [f'{i["title"]}: {i["why"]}' if i["why"] else i["title"] for i in top]


def make_period(pid: str, kind: str, label: str, start: date, end: date,
                days: list[dict], note: str = "") -> dict | None:
    inside = [d for d in days if start.isoformat() <= d["date"] <= end.isoformat()]
    if not inside:
        return None
    news, regs = roll_up(inside, kind)
    if not news and not regs:
        return None
    written = read_json(SUMMARIES / f"{pid}.json", {})
    headline, summary = fallback_summary(news, regs)
    if isinstance(written, dict) and written.get("summary"):
        headline = str(written.get("headline") or headline)
        summary = [str(s) for s in written["summary"]][:6]
    first, last = inside[0]["date"], inside[-1]["date"]
    return {
        "id": pid, "kind": kind, "label": label, "note": note,
        "start": start.isoformat(), "end": end.isoformat(),
        "first_day": first, "last_day": last, "days": len(inside),
        "scanned": sum(d["scanned"] for d in inside),
        "headline": headline, "summary": summary,
        "summary_by": "claude" if isinstance(written, dict) and written.get("summary") else "auto",
        "items": news, "regulatory": regs,
    }


def periods(days: list[dict], today: date) -> list[dict]:
    out = []
    if not days:
        return out
    oldest = date.fromisoformat(days[0]["date"])
    # weekly
    this_monday = monday(today)
    for k in range(WEEKS_SHOWN):
        a = this_monday - timedelta(weeks=k)
        b = a + timedelta(days=6)
        if b < oldest:
            break
        y, w, _ = a.isocalendar()
        p = make_period(f"{y}-W{w:02d}", "week", fmt_range(a, b), a, b, days,
                        "this week, so far" if k == 0 else "")
        if p:
            out.append(p)
    # monthly: completed months
    y, m = today.year, today.month
    for _ in range(MONTHS_SHOWN):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        a, b = date(y, m, 1), month_end(y, m)
        if b < oldest:
            break
        p = make_period(f"{y}-{m:02d}", "month", f"{a:%B %Y}", a, b, days)
        if p:
            if p["first_day"] > a.isoformat():
                p["note"] = f"from {date.fromisoformat(p['first_day']):%b} {date.fromisoformat(p['first_day']).day}"
            out.append(p)
    # quarterly: completed quarters
    y, q = today.year, quarter_of(today)
    while True:
        y, q = (y - 1, 4) if q == 1 else (y, q - 1)
        a, b = date(y, 3 * q - 2, 1), month_end(y, 3 * q)
        if b < oldest:
            break
        p = make_period(f"{y}-Q{q}", "quarter", f"Q{q} {y}", a, b, days)
        if p:
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scout", type=Path, nargs="?", help="PuratosScouting checkout (optional: "
                    "without it, only rebuilds periods from the archive and summaries)")
    ap.add_argument("--today", default=None, help="for testing: pretend today is YYYY-MM-DD")
    a = ap.parse_args()

    if a.scout:
        print(f"archive: {archive_from_scout(a.scout)} day file(s) added or updated")
    days = sorted((d for d in (read_json(p, None) for p in ARCHIVE.glob("*.json")) if d),
                  key=lambda d: d["date"])
    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    ps = periods(days, today)
    if not ps:
        print("no archived days yet; leaving news/latest.json unchanged", file=sys.stderr)
        return 0
    old = read_json(OUT, {})
    if old.get("periods") == ps:
        print("news unchanged since the last run")
        return 0
    write_if_changed(OUT, {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                           "periods": ps})
    print(f"wrote {OUT}: " + ", ".join(f'{p["id"]} ({p["summary_by"]})' for p in ps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
