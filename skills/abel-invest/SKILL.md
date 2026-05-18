---
name: abel-invest
description: >
  Use when the user wants Abel strategy discovery, candidate screening,
  graph-grounded trading research, or continuing/preparing/debugging an Abel
  strategy discovery workspace.
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# Abel Strategy Discovery

Use this skill for:

- strategy discovery and candidate screening
- continuing an existing Abel strategy discovery workspace
- creating sessions and branches
- preparing, debugging, recording, and reviewing research rounds
- interpreting `evidence_ledger.json`, `frontier.md`, `agent_context.md`, and
  `research_journal.md`

## Activation Checklist

Always start by resolving workspace state before strategy work.

1. Read `references/workspace-bootstrap.md`.
2. Resolve the workspace context:
   - if `alpha.workspace.yaml` is in the current directory, use the current
     directory
   - else if `abel-invest-workspace/alpha.workspace.yaml` exists
     under the current directory, use that child workspace
   - else bootstrap a workspace before deep research work
3. Prefer `abel-invest workspace context --path . --json` once the CLI is
   installed; use its `workspace_root` and `research_root` instead of guessing
   from directory names.
4. Baseline-first: before from-scratch discovery, check whether a validated
   strategy for this target already exists in any baseline / strategy catalog
   the user maintains. If one exists, treat it as the baseline and ceiling and
   iterate from it; do not rediscover from scratch.
5. Run `abel-invest doctor --path <workspace-root>`.
6. If doctor reports `auth_missing`, use `abel-auth`, then rerun doctor.
7. Only start or continue session/branch work after doctor is ready, unless the
   user explicitly asks you to inspect or repair setup.

## Reference Routing

- New workspace, workspace reuse, auth, doctor, or setup repair:
  read `references/workspace-bootstrap.md`.
- New session, normal round loop, or resuming a session:
  read `references/experiment-loop.md`.
- Live graph discovery, graph frontier expansion, or graph-first reasoning:
  read `references/discovery-protocol.md`.
- Creating or revising `branch.yaml`, reviewing evidence labels,
  journal coverage, input realization, or research journal use:
  read `references/branch-authoring.md`.
- Writing `engine.py`, handling semantic/runtime failures, or checking
  temporal legality:
  read `references/constraints.md`.
- Explaining why the workflow is graph-first or evidence-boundary oriented:
  optionally read `references/methodology.md`.
- Forming the candidate space (entry stance, feature generation, ensemble):
  read `references/data-driven-construction.md`. Core path.
- Choosing concrete constructions while writing the engine:
  read `references/proven-patterns.md` (battle-tested patterns). Core path.
- A hard Sharpe / MaxDD / PnL target is set:
  read `references/guarded-optimization.md` (self-contained gauntlet-gated
  optimization). Core path — not optional — when a performance bar is set.

## Operating Rules

1. Treat this as a workspace-first flow, not a one-shot answer flow.
2. Reuse the default workspace when it already exists.
3. Bootstrap the workspace before deep strategy work when it does not exist yet.
4. Use `abel-invest` commands, not old command aliases.
5. On a fresh skill install where `abel-invest` is not available yet, use
   `python3 <abel-invest-skill-root>/scripts/bootstrap_workspace.py --path abel-invest-workspace`.
   Do not import `abel_invest` with the system interpreter for bootstrap.
6. Reuse existing Abel auth first. If live access is still missing, use
   `abel-auth`.
7. Treat `branch.yaml` as a research declaration, not evidence truth.
8. Treat `evidence_ledger.json` and `frontier.md` as factual evidence surfaces,
   not generated strategy advice.
9. Treat `agent_context.md` as the compact factual resume surface and
   `research_journal.md` as agent-owned research state.
10. New sessions are graph-first: live causal graph discovery initializes
   `graph_frontier.json`. Expand graph breadth only when a frontier question
   remains after reading current evidence; do not expand just because a small
   number of branches failed.
11. Graph breadth should not outrun mechanism depth. Before expanding to a
    more distant frontier, ask whether the current graph neighborhood still has
    an unresolved sign, lag, regime, interaction, control, or risk-shaping
    question. If yes, prefer one mechanism-deepening branch over distant graph
    expansion.
12. Do not treat branch count as proof of breadth. Graph-node concentration,
   strategy-variant coverage, and local refinement pressure are separate facts.
13. Do not call parameter, sizing, threshold, filter, or window tweaks broad
    exploration. Name search width honestly; do not relabel it.
14. Mechanism and graph priors SEED candidates; optimization toward the
    objective is a first-class path, not a deviation, when it runs as GUARDED
    optimization: the causal-graph prior bounds the search space, and every
    candidate must clear the full gauntlet (semantic preflight, the standard
    gate/DSR/triangle profile, leakage, walk-forward) before it can be selected.
    The failure mode to avoid is selecting on a raw metric WITHOUT the gauntlet,
    not optimization itself. See `references/guarded-optimization.md`.
15. `--selection-trials N` is the honest K-accounting that MAKES guarded
    optimization legitimate: it deflates DSR by the true number of variants
    tried. Always pass it for any search width. It is mandatory for guarded
    optimization, not a marker of misbehavior.
16. A hard user metric target (Sharpe / MaxDD / PnL) IS an optimization
    request. Pursue it via guarded optimization (gauntlet-gated,
    causal-prior-bounded, K-accounted) — not by widening un-gated local search,
    and not by declining and reporting short. Report the gauntlet-surviving
    optimum honestly; never game a metric outside the gauntlet. abel-invest runs
    this itself; do not depend on any external skill.
17. CAP graph nodes are model-supported causal priors. Trust that they carry
    target-relevant information, but do not infer disclosed weight, exact lag,
    signed effect, or tradable direction from the role alone. Parent and child
    roles disclose causal-flow orientation; Abel Invest's `blanket` role is a
    Markov-blanket discovery bucket, not a fixed causal-flow direction.
18. When using CAP graph nodes in a branch, state the graph use contract before
    treating the round as graph-supported candidate evidence: selected nodes,
    construction, intended role, unresolved assumption, and falsification
    scope. This contract describes the agent's current use of the nodes; it is
    not a fixed role implied by the graph.
19. If a branch combines multiple graph nodes as one same-direction,
    equal-weight, or same-lag basket, declare that construction explicitly. A
    failed basket only invalidates that construction unless other evidence
    supports a broader graph conclusion.
20. Abel Ask or narrative context may generate mechanism hypotheses, supplement
    drivers, or graph expansion questions, but it is scout context, not
    validation evidence.
21. Use one narrative scout pass when the next research decision is ambiguous
    between mechanism-deepening, graph expansion, or stopping, especially when
    the current graph neighborhood has no clear real-world mechanism. Record
    off-target, weak, unavailable, or skipped narrative scout plainly; do not
    force it into branch evidence.
22. Every recorded round requires an agent-written `research_journal.md` entry
    with the round ledger reference before the next recorded round.
23. Treat input realization as an evidence fact: a graph-supported declaration
    only becomes graph-supported evidence when runtime reads the prepared graph
    inputs. When graph-node reads are inferred from asset reads, preserve that
    source as a fact rather than overstating edge-native field-level proof.
24. Create new sessions only after workspace context resolves. Do not use
    `--root` unless intentionally creating a legacy/offline session, and then
    pass `--allow-outside-workspace`.
25. Do not create or refresh an online session view automatically. When the
    strategy context is mature enough to be useful to review visually, ask the
    user whether to visualize the session. This can be after a strong candidate
    PASS, after several informative candidate rounds, before promotion, or
    whenever the agent would naturally summarize that the strategy is worth a
    visual review. Do not print a command for the user to run. If the user
    agrees, or if the user explicitly asks to visualize the session, run
    `abel-invest visualize-session --session <session> --with-strategy-artifact`
    yourself and share the returned Markdown link. This is the default
    visualization path because the online review should include the selected
    best `PASS` strategy artifact when one is available. Use narrative-only
    `visualize-session` only when the user explicitly asks for a session view
    without strategy artifact upload. Session views are incremental: running
    `visualize-session` again updates the online view with the latest local
    session evidence, rounds, and selected strategy artifact when one is
    available.
    If that command reports `needs_agent_refactor`, read the emitted
    `refactor-request.json` and handle it in this same skill loop. If `kind`
    is `state_intent_self_check`, inspect the selected branch source and nearby
    model/checkpoint/cache files, then write `state_intent.json`: either
    classify every durable state file required for paper startup, or explicitly
    write an empty `entries` list with a `selfCheck` summary explaining why the
    detected files are not durable paper state. If `kind` is `agent_assisted`,
    edit only the promoted copy named there, write `refactor-report.json`, and
    rerun the same command. Do not start a separate agent process or ask the
    user to trigger a second publish attempt.
26. The default Abel router base URL is `https://api.abel.ai/router/`.
    `abel-auth` owns API key setup. Do not ask the user or agent to provide a
    router URL unless they are intentionally testing another router.
27. The framework defines evidence validity. The agent owns the strategy
    thinking.
