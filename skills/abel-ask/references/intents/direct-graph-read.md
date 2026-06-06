# Direct Graph Read

Use when the user asks about a specific ticker, node, path, neighborhood,
driver, parent/child relation, or graph fact.

This intent usually executes through `direct_graph`.

## Workflow

1. Answer the literal graph question first.
2. For tickers or named assets, inspect both price and volume neighborhoods when
   relevant.
3. Use node descriptions before writing visible labels.
4. Challenge the read with reverse paths, sibling/blanket confounders,
   deconsensus, or fragility when the answer is non-trivial.
5. Use web grounding only when freshness or external facts materially affect the
   answer.

Ticker names may remain visible if the user asked about them. Raw node ids,
paths, payloads, and model decimals stay internal unless the user asks for raw
output.
