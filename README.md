# NAM-Incubation-hub
Business case to have a start up incubator part of broader Puratos. 

## Business case website

`index.html` is the clickable business case ("The Proofing Room"). It is a single self-contained page, served with GitHub Pages from the `main` branch root.

## Food-tech news tab

The "Food-tech news" tab summarises the Food-Tech Scout (private repo
`Judybunwang/PuratosScouting`) by period. Its dropdown lists the last 5 weeks, then each
completed month, then each completed quarter (Q1-Q4), so it rolls up as history builds.
Each period shows a headline, an executive summary and its top stories, with filters by
business unit.

- `news/archive/<day>.json`: each scored day's candidate items and Claude's daily notes,
  kept here so history outlives the scout's own retention window.
- `news/summaries/<period>.json`: Claude-written headline and executive summary per
  week, month or quarter (see that folder's README). Without one, the page shows the
  period's top stories at a glance.
- `news/latest.json`: what the page reads, built by `scripts/build_news.py`.
- `.github/workflows/news.yml` runs it every day (12:30 and 16:30 UTC) and commits changes.
- One-time setup: add a repository secret `SCOUT_REPO_TOKEN`, a fine-grained personal
  access token with read-only Contents access to `Judybunwang/PuratosScouting`.
  You can also run the workflow by hand from the Actions tab.
