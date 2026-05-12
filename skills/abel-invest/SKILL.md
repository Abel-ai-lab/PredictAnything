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
4. Run `abel-invest doctor --path <workspace-root>`.
5. If doctor reports `auth_missing`, use `abel-auth`, then rerun doctor.
6. Only start or continue session/branch work after doctor is ready, unless the
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
- Looking for mechanism inspiration after the branch workflow is already
  runnable:
  optionally read `references/proven-patterns.md`.

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
    exploration.
14. Standard discovery chooses branches from graph context, mechanism
    reasoning, recorded evidence, or explicit control/ablation purpose before
    metric search. Do not run local parameter, threshold, window, filter,
    sizing, driver, or asset sweeps to choose a branch candidate unless the user
    explicitly requests optimization.
15. Treat `--selection-trials` as DSR audit and penalty accounting, not as
    permission to use brute-force candidate selection in standard discovery.
16. Treat user metric targets such as Sharpe thresholds as success criteria, not
    as optimization permission. Report evidence honestly or ask for explicit
    optimization rather than widening local search just to satisfy a target.
17. CAP graph nodes are causal priors, not trading directions. They do not
    provide sign, lag, or monotone strength; deeper nodes are weaker or more
    indirect priors unless recorded evidence or domain context justifies them.
18. Abel Ask or narrative context may generate mechanism hypotheses, supplement
    drivers, or graph expansion questions, but it is scout context, not
    validation evidence.
19. Use one narrative scout pass when the next research decision is ambiguous
    between mechanism-deepening, graph expansion, or stopping, especially when
    the current graph neighborhood has no clear real-world mechanism. Record
    off-target, weak, unavailable, or skipped narrative scout plainly; do not
    force it into branch evidence.
20. Every recorded round requires an agent-written `research_journal.md` entry
    with the round ledger reference before the next recorded round.
21. Treat input realization as an evidence fact: a graph-supported declaration
    only becomes graph-supported evidence when runtime reads the prepared graph
    inputs. When graph-node reads are inferred from asset reads, preserve that
    source as a fact rather than overstating edge-native field-level proof.
22. Create new sessions only after workspace context resolves. Do not use
    `--root` unless intentionally creating a legacy/offline session, and then
    pass `--allow-outside-workspace`.
23. Do not create or refresh an online session view automatically. When the
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
    session evidence, rounds, primary strategy, and artifacts.
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
24. The default Abel router base URL is `https://api.abel.ai/router/`.
    `abel-auth` owns API key setup. Do not ask the user or agent to provide a
    router URL unless they are intentionally testing another router.
25. The framework defines evidence validity. The agent owns the strategy
    thinking.
