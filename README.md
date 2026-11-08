# NAM-Incubation-hub
Business case to have a start up incubator part of broader Puratos. 

## Business case website

`index.html` is the clickable business case ("The Proofing Room"). It is a single self-contained page, served with GitHub Pages from the `main` branch root.

## Food-tech news tab

The "Food-tech news" tab shows the latest daily brief from the Food-Tech Scout
(private repo `Judybunwang/PuratosScouting`): Claude's headline and executive summary,
then the top items by business unit, with a picker for the last 14 days.

- `news/latest.json` holds the briefs; the page reads it when the tab loads.
- `.github/workflows/news.yml` rebuilds it every day (12:30 and 16:30 UTC, after the
  scout's morning scoring) with `scripts/build_news.py` and commits it when it changed.
- One-time setup: add a repository secret `SCOUT_REPO_TOKEN`, a fine-grained personal
  access token with read-only Contents access to `Judybunwang/PuratosScouting`.
  You can also run the workflow by hand from the Actions tab.
