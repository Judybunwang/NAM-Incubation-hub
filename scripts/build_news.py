"""Build news/latest.json for the "Food-tech news" tab from a Food-Tech Scout checkout.

Usage: python scripts/build_news.py PATH_TO_PURATOSSCOUTING [--days 14]

It reads the scout's stored items (data/items.json), Claude's daily headline and
executive summary (data/claude/<day>.json) and the newsletter thresholds in
config.toml, and picks each day's items the same way the daily email does:
relevance 6+ for news (max 30), 5+ for regulatory items (max 8).
Standard library only, so the GitHub Action needs no installs.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "news" / "latest.json"


def safe_url(u: str) -> str:
    u = (u or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def slim(it: dict) -> dict:
    return {
        "title": it.get("title", ""),
        "url": safe_url(it.get("url", "")),
        "source": it.get("source", "").replace("Google News: ", ""),
        "kind": it.get("kind", ""),
        "published": it.get("published", ""),
        "unit": it.get("primary_bu", ""),
        "scores": {k: round(v) for k, v in (it.get("bu_scores") or {}).items()},
        "relevance": round(it.get("relevance", 0)),
        "horizon": it.get("horizon", ""),
        "category": it.get("category", ""),
        "region": it.get("region", ""),
        "summary": it.get("ai_summary") or "",
        "why": it.get("why_it_matters") or "",
        "image": safe_url(it.get("image", "")),
        "entities": (it.get("entities") or [])[:6],
    }


def select(items: list[dict], g: dict) -> tuple[list[dict], list[dict]]:
    rank = lambda i: (i.get("relevance", 0), i.get("prefilter", 0))  # noqa: E731
    regs = sorted((i for i in items if i.get("kind") == "regulation"
                   and i.get("relevance", 0) >= g.get("regulatory_min_relevance", 5)),
                  key=rank, reverse=True)
    rest = sorted((i for i in items if i.get("kind") != "regulation"
                   and i.get("relevance", 0) >= g.get("newsletter_min_relevance", 6)),
                  key=rank, reverse=True)
    return rest[: g.get("newsletter_max_items", 30)], regs[: g.get("regulatory_max_items", 8)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scout", type=Path)
    ap.add_argument("--days", type=int, default=14)
    a = ap.parse_args()

    g = tomllib.loads((a.scout / "config.toml").read_text())["general"]
    items = json.loads((a.scout / "data" / "items.json").read_text())
    scored_days = sorted((p.stem for p in (a.scout / "data" / "claude").glob("*.json")), reverse=True)

    issues = []
    for day in scored_days:
        if len(issues) >= a.days:
            break
        todays = [i for i in items if i.get("first_seen") == day]
        news, regs = select(todays, g)
        if not news and not regs:
            continue
        try:
            notes = json.loads((a.scout / "data" / "claude" / f"{day}.json").read_text())
        except (OSError, ValueError):
            notes = {}
        issues.append({
            "date": day,
            "headline": str(notes.get("headline", "")).strip(),
            "summary": [str(s) for s in (notes.get("executive_summary") or [])][:5],
            "scanned": len(todays),
            "items": [slim(i) for i in news],
            "regulatory": [slim(i) for i in regs],
        })

    if not issues:
        print("no scored days found; leaving news/latest.json unchanged", file=sys.stderr)
        return 0
    try:
        if json.loads(OUT.read_text()).get("issues") == issues:
            print("news unchanged since the last run")
            return 0
    except (OSError, ValueError):
        pass
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "issues": issues,
    }, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT} with {len(issues)} issues, latest {issues[0]['date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
