# Period summaries

One file per period shown in the "Food-tech news" dropdown: `2026-W45.json` (ISO week),
`2026-10.json` (month), `2026-Q4.json` (quarter). Shape:

    {"headline": "one line, max 110 characters", "summary": ["3 to 5 one-sentence takeaways"]}

`scripts/build_news.py` uses a file here when it exists, otherwise it builds a simple
summary from the period's top items. A weekly scheduled Claude task writes these every
Monday for the week just finished, and for the month or quarter when one has just ended.
