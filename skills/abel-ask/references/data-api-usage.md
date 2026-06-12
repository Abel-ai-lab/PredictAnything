# Abel Data API Usage

Use this reference when a task needs supplemental structured datasets exposed
through the Abel gateway.

## When to Use

Use the data API when the user asks for concrete structured facts, historical
time windows, comparisons, screening, ranking, reproducible evidence, or when a
causal read needs underlying series such as prices, fundamentals, macro,
filings, trade, transport, weather, or other listed catalog datasets.

Do not use the data API for pure concept explanations, writing-only tasks, or
when graph and narrative probes are sufficient.

## Environment

The script defaults to production:

```bash
python3 scripts/data_api.py catalog
```

Select SIT explicitly:

```bash
python3 scripts/data_api.py --target-env sit catalog
```

Production and SIT gateway roots:

- `prod`: `https://cap.abel.ai/data-infra`
- `sit`: `https://cap-sit.abel.ai/data-infra`

Override with `--base-url` or `ABEL_DATA_API_BASE_URL` only when a task points
to a custom gateway.

## Auth

The script uses the same auth discovery as other Abel scripts and sends only:

```http
Authorization: Bearer <api-key>
```

Do not send `api-key`, `user-tier`, or `fee-level`; those headers are internal
gateway-to-service headers.

Check auth before data work when token availability is unclear:

```bash
python3 scripts/data_api.py auth-status
```

The script searches shared Abel auth locations for `ABEL_API_KEY` or
`CAP_API_KEY`, so normally do not pass `--api-key` manually.

## Workflow

1. Run `catalog` first. Treat the response as the current key's visible dataset
   list.
2. If `catalog` returns an empty dataset list, stop immediately. This is a
   hard stop, not a soft warning: do not call `schema`, do not call `records`,
   and do not use dataset names from examples, memory, another environment, or
   another key. An empty catalog usually means the key, such as a free-tier key,
   has no currently visible supplemental datasets.
3. Use the returned dataset `name` exactly as provided. Do not infer table
   names.
4. Run `schema <name>` before querying records.
5. Query `records <name>` with schema-declared filters and date bounds.
6. Follow `nextCursor` until absent when more rows are needed.
7. A 403 from `schema` or `records` means the key cannot access that dataset.
8. Inspect `ok`, `status_code`, and `message` before trusting returned data.

Use `--compact` and `--pick-fields` when responses are large or only specific
fields are needed in context.

## Examples

```bash
python3 scripts/data_api.py auth-status
python3 scripts/data_api.py catalog --q price
python3 scripts/data_api.py catalog --compact --pick-fields data
python3 scripts/data_api.py schema market.price.daily
python3 scripts/data_api.py records market.price.daily --start-date 2025-01-01 --end-date 2025-01-31 --param symbol=AAPL --limit 100
python3 scripts/data_api.py records market.price.daily --cursor <nextCursor> --limit 100
```
