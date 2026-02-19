# X Protocol Crawler

Protocol crawler for searching posts by account + keyword on X and exporting JSONL output.
Data collection runs on pure protocol requests (`httpx`) with dynamic `x-client-transaction-id`
generated in-repo.

## Structure

- `docs/PRD.md`
- `docs/TECH.md`
- `docs/INTERFACE.md`
- `docs/update.md`
- `js/analysis/`
- `js/dist/`
- `js/docs/`
- `src/`
- `tests/`
- `scripts/`
- `debug/`
- `output/`

## Run

```bash
python run.py <start_date> <end_date>
```

With account pool:

```bash
python run.py <start_date> <end_date> --cookies-pool-file docs/CookiesPool.txt
```

Date format: `YYYY_M_D` (inclusive boundary days).

Each run writes:
- Data: `output/<run_id>/data.jsonl`
- Full runtime log: `output/<run_id>/crawl.log`

## Keyword Rules (`docs/Keys.txt`)

- One line = one keyword rule.
- Multiple terms in the same line are **AND** logic (all terms must be hit).
  - separators supported: spaces, `,`, `，`, `+`
- Different lines are **OR** logic (any rule hit will be written).

## Rate-Limit Behavior

- When X returns `429`, the crawler waits by `x-rate-limit-reset` first.
- If no reset header exists, it uses conservative fallback waiting.
- Quota-aware proactive scheduling is enabled:
  when `x-rate-limit-remaining <= X_RATE_LIMIT_PROACTIVE_THRESHOLD`,
  next request waits until reset window to reduce continuous `429`.

## Account Pool

- `--cookies-pool-file` is optional; each line is one `cookies.json` path.
- The primary `--cookies-file` is always included as slot 1.
- Slots are used in round-robin per `(account, keyword)` task.
- If one slot auth expires, only that slot auto-relogs.
