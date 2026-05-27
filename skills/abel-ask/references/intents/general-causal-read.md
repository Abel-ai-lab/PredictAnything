# General Causal Read

Use when the user asks how one real-world thing affects another, what mechanism
connects them, or why an outcome is happening, without asking for a shortlist or
trade.

Usually execute through `proxy_routed` unless the user supplied graph-ready
anchors.

## Workflow

1. Rewrite the question as `cause -> mechanism -> outcome`.
2. Generate the obvious mechanism, a second-order mechanism, a contrarian, and a
   confounder.
3. Map each mechanism to graph-ready anchors or mark it web-only.
4. Use graph structure to test plausibility and find contradictions.
5. Use focused web evidence for freshness, policy, user behavior, or facts not
   represented in the graph.
6. Answer with the strongest mechanism, the weakest link, and what would change
   the conclusion.
