# Changelog

All notable changes to `causal-abel` will be documented in this file.

This project follows a repo-level release log so agents can summarize user-visible changes across GitHub and ClawHub-facing revisions.

## [1.5.0] - 2026-05-21

### Added

- Added default Abel Invest session visualization strategy-artifact upload, including hosted artifact manifests, trade-log packaging, and dashboard-compatible selection metadata.
- Added the data-driven Abel Invest alpha-search posture, emphasizing graph-enriched empirical construction, feature factories, guarded optimization, and ledger-grounded exploration evidence.

### Changed

- Updated Abel Invest to version `3.6.0` and kept the Abel Edge runtime dependency on `>=0.8.6,<0.9.0`.
- Retuned Abel Invest strategy artifact selection toward Sharpe, annual return, drawdown, and pass-rate ranking while preserving dashboard-compatible upload metadata.
- Refined Abel Invest workspace, exploration-path, frontier, and experiment-loop guidance around graph-informed data search without turning research process into rigid strategy advice.

### Fixed

- Allowed hostable validation strategy artifacts to be selected from robust non-PASS rounds when they contain the required engine, result, metrics, and promotion evidence.
- Preserved SIT/prod router compatibility by keeping runtime endpoint selection outside Abel Skills product defaults.

## [1.4.0] - 2026-05-18

### Added

- Added Abel Invest hosted strategy artifact promotion, upload, manifest, and replay flows so session visualization can include selected PASS strategy artifacts.
- Added workspace runtime freshness checks so updated Abel Invest skills can detect stale existing workspaces and route agents through `env refresh`.
- Added expanded strategy-artifact and workspace environment tests covering refactor handoffs, doctor freshness reporting, and workspace-local command behavior.

### Changed

- Updated Abel Invest to version `3.5.3` and raised the Abel Edge minimum dependency to the current supported runtime line.
- Updated Abel Invest guidance to prefer workspace-local command prefixes instead of assuming `abel-invest` is available on the global PATH.
- Tightened Abel auth and router skill probe guidance so shared Abel helper commands resolve relative to the installed skill root rather than the current working directory.
- Refined graph-use, discovery-discipline, visualization timing, and strategy-artifact guidance for agent-led Abel Invest research.

### Fixed

- Preserved null values for inapplicable artifact metrics instead of forcing misleading numeric values.
- Removed stale visualization and promote-branch fallbacks that conflicted with the strategy-artifact-first publishing path.

## [1.3.0] - 2026-05-09

### Added

- Added Abel Invest graph-frontier strategy discovery flows, session-first dashboard upload support, and primary strategy selection for dashboard sessions.
- Added primary strategy trade-log CSV generation and upload support so downstream dashboard strategy detail can render backtest time series from stored trade logs.
- Added DSR accounting audit trail support and expanded primary strategy metrics, including DSR, loss years, and position IC stability.

### Changed

- Refactored Abel Invest narrative implementation into `narrative_core` and workspace support into `workspace_core` while preserving public CLI entrypoints.
- Updated Abel Invest workspace bootstrap, branch authoring, discovery protocol, and experiment-loop guidance for graph-first strategy discovery.

## [1.2.0] - 2026-04-28

### Added

- Added native OpenClaw plugin packaging for Abel, bundling the router, auth, causal-read, investment-discovery, and shared probe skills into one ClawHub package.
- Added OpenClaw config discovery for Abel auth, including `skills.entries.abel.apiKey` and legacy `skills.entries.causal-abel.apiKey`.
- Added the required no-op OpenClaw extension entry so ClawHub can publish the skill bundle as a native code plugin.

### Changed

- Updated ClawHub publishing to use `clawhub package publish` with source metadata and OpenClaw compatibility fields.
- Updated OpenClaw-facing auth guidance so agents persist keys through OpenClaw config management instead of treating `.env.skill` as the primary path.

## [1.1.6] - 2026-04-10

### Added

- Added an `auth-status` command to `skills/causal-abel/scripts/cap_probe.py` so agents can check auth readiness and source without exposing the key.

### Changed

- Tightened `causal-abel` preflight guidance so live runs start with `auth-status`, treat `.env.skill` as a first-class local auth source, and stop to ask the user before starting OAuth.
- Tightened the missing-auth flow so agents do not fall back to web search merely because Abel auth is unavailable.

## [1.1.5] - 2026-04-10

### Added

- Added a maintainer smoke probe runner for rendered local `causal-abel` installs, covering query-node ranking checks, `observe-dual`, `paths`, `intervene-do`, and `intervene-time-lag`.

### Changed

- Updated bundled probe normalization so macro-capable graph reads keep canonical macro node ids across `normalize-node` and `paths` instead of coercing them into asset-only suffixes.
- Updated routing and probe guidance so `extensions.abel.query_node` results inspect `node_kind` before choosing the next surface, making macro hits route through direct graph-capable verbs instead of asset-only shortcuts.
- Updated local auth lookup so the bundled probe can fall back to a same-directory `.env` when `.env.skill` or `.env.skills` is absent.

## [1.1.4] - 2026-04-01

### Added

- Added an `observe-dual` helper to `scripts/cap_probe.py` so agents can probe both `price` and `volume` surfaces in one call before choosing the first-pass executable anchor.

### Changed

- Updated direct-graph routing guidance to default liquid-name driver reads to a paired `price` + `volume` observational pass instead of assuming `price` is the only meaningful first anchor.
- Tightened probe guidance so agents explicitly carry forward whichever surface materializes (`price`, `volume`, or both`) before running deeper structural reads or pressure tests.

## [1.1.3] - 2026-03-31

### Changed

- Removed the `appendix`-as-default output shape from the source `causal-abel` guidance so the normal response now defaults to the main answer only unless the user explicitly asks for trace, evidence, debug, or reproducibility details.
- Reworked rendering guidance from explicit `render_map` language to a lighter `label pass` flow, reducing the chance that internal rendering artifacts leak into visible prose.
- Tightened source report rules so raw graph identifiers, raw proxy tickers, paths, prediction decimals, and process transcripts stay internal by default, with the normal answer explicitly avoiding debug-style headings and dumps.

## [1.1.2] - 2026-03-31

### Added

- A dedicated `references/routes/proxy-routed.md` route file so the main skill can stay focused on orchestration while proxy-routed reads keep their deeper graph workflow in one place.
- An event-driven `unstable-premise` gate for recent leaks, launches, shutdowns, partnerships, and org changes, requiring a minimal premise check before normal graph expansion.

### Changed

- Tightened `causal-abel` trigger wording and `agents/openai.yaml` metadata so the skill still covers broad dollar-value decisions without relying on generic phrases like `should I` or `worth it`.
- Refactored the main `SKILL.md` into a lighter dispatcher with hard gates, stop rules, and references, moving repeated execution detail into route/reference files.
- Added an `opportunity-scope` gate so broad asks like `有什么赚钱机会` lock a primary frame first instead of mixing public-market, supplier, startup, and career/business opportunities into one mechanism list.
- Updated web-grounding rules so freshness-sensitive opportunity reads separate verifiable subclaims from inferred strategy claims and downgrade to conditional analysis when the premise is not yet anchored.

## [1.1.1] - 2026-03-30

### Changed

- Centralized time-sensitive source hierarchy and claim-downgrade rules in `references/web-grounding.md` instead of repeating them across multiple skill files.
- Simplified `agents/openai.yaml` and the ClawHub build template so UI metadata stays short and skill-specific, with execution detail kept in the skill body and references.

## [1.1.0] - 2026-03-30

### Added

- A multi-tier proxy-routed analysis flow that moves from hypothesis generation to graph screening, deeper structural reasoning, and intervention-backed verification for broader dollar-value decisions.
- Dedicated rendering guidance and a `scripts/render_guard.py` helper so visible answers are checked for ticker-heavy leakage before finalization.
- Stronger answer-shaping guidance for decision archetypes such as timing, ROI, allocation, regret minimization, and graph-sparse reads.

### Changed

- Expanded `causal-abel` from market/business/crypto-only reads to broader dollar-value decisions, including career, education, housing, lifestyle, and macro questions routed through Abel market proxies.
- Reworked the main skill instructions into a more direct end-to-end flow, while trimming dead references and fixing route guidance that pointed to removed files.
- Tightened visible-answer rendering so agents run `node_description` on the final shortlist, prefer company / industry / product / role labels over raw tickers, and only keep a ticker in the verdict when the user explicitly asked about that named asset.
- Restored adaptive `horizon_steps` guidance for `intervene_time_lag`, including the `6 -> 24/42 -> 170` widening ladder and medium-range default of `~24` when the prompt does not specify a window.
- Refined web-grounding and direct-graph rules so graph facts stay primary, graph-sparse handling is explicit, and direct ticker reads no longer depend on stale or contradictory routing notes.
- Updated the report guide so verdict-layer rendering, proxy-life-decision boundaries, causal-chain writing, and action-oriented conclusions are more explicit.

## [1.0.10] - 2026-03-27

### Changed

- Removed `low-signal` wording from the source `causal-abel` planner and report guidance, replacing it with softer bridge-heavy / diffuse / non-explanatory phrasing so internal routing heuristics do not leak into user-facing language.
- Refined direct-graph interpretation guidance so surprising drivers are explained via the security's own attributes before falling back to `weak` or `unresolved` wording.
- Trimmed `causal-abel/agents/openai.yaml` back toward trigger and routing guidance so detailed execution rules stay in `SKILL.md` and route references.
- Tightened the source `causal-abel` prompt so the core guidance is shorter and higher-leverage, with graph-first rules phrased as a small set of primary constraints.
- Refined broad ticker-driver guidance so agents anchor to executable tickers, run Abel first, and interpret surprising parents as transmission channels before leaving the graph.
- Tightened `causal-abel` prompt priority so direct graph answers now preserve graph facts first instead of replacing them with web-searched narratives.
- Reframed Abel graph outputs as high-value PCMCI-style market-data evidence and added guidance for handling surprising drivers as serious transmission signals.
- Narrowed direct-graph web grounding so driver lists, parent membership checks, and path facts are usually answered from graph output without forced search.
- Updated the report and planner guidance so graph fact, interpretation, and optional web validation stay visibly separate when the graph output is unintuitive.
- Reframed `causal-abel` so the default output shape is a compact report rather than a short verdict-only answer.
- Updated the direct and proxy routes so executable anchors are observed first, preferring `extensions.abel.observe_predict_resolved_time` before deeper structural traversal.
- Changed the planner and probe guidance so non-trivial comparative reads now default to one compact `intervene.do` pressure test after the mechanism is coherent.
- Updated the report template so pressure-test coverage is expected by default in longer comparative analyses.

## [1.0.2] - 2026-03-24

### Added

- `references/search-loop.md` for edge-anchored search discipline in proxy-routed reads.
- `references/layered-routing.md` for selecting layered proxy anchors and running convergence reads on broad questions.

### Changed

- Expanded the source and committed ClawHub skill instructions with `convergence_read`, stronger proxy/search guardrails, and clearer separation between graph facts, searched mechanisms, and inference.
- Updated `question-routing.md`, `inversion-flow.md`, and `probe-usage.md` to support layered proxy routing, search-loop escalation, and convergence-first analysis for broad comparisons.
- Updated `cap_probe.py` so `intervene-do` performs a required `graph.paths` gate before calling `intervene.do`, and added `--max-description-chars` for trimming verbose text fields in responses.
- Refined first-use update wording so the skill prompts on version differences without depending on an in-prompt changelog summary.
- Restored the repository changelog as the source of release notes for update and publish flows, while keeping the generated ClawHub artifact free of source-only update metadata.
- Bumped the source skill and committed ClawHub artifact to version `1.0.2`.

## [1.0.1] - 2026-03-23

### Added

- Explicit `metadata.openclaw` runtime requirements in `SKILL.md` for ClawHub publishing.
- A root build script at `scripts/build_clawhub_release.py` that assembles a ClawHub-ready artifact in `dist/clawhub/causal-abel`.

### Changed

- Reworked the main skill instructions to fit ClawHub and OpenClaw installs without assuming a GitHub-first self-update flow.
- Simplified `agents/openai.yaml` so the default prompt focuses on authorization and causal routing.
- Updated probe examples to use bundled relative paths such as `scripts/cap_probe.py`, which work cleanly after installation.
- Reframed update guidance so published installs prefer `clawhub update causal-abel` instead of `npx skills` refresh commands.
- Restored the source `causal-abel` skill as the full legacy-aware variant with first-use soft update guidance.
- Switched the release model from runtime environment detection to build-time packaging, so ClawHub can receive a stripped variant with no automatic update mechanism.
- Kept `metadata.openclaw` in the source skill so ClawHub requirements remain explicit even though the published artifact is generated.

## [1.0.0] - 2026-03-23

### Added

- Explicit skill version metadata in `SKILL.md`.
- A repository `CHANGELOG.md` for release summaries.
- A bundled `scripts/check_skill_update.py` helper that runs `npx skills check`, reads the remote `SKILL.md` and `CHANGELOG.md`, and returns a machine-readable update summary.

### Changed

- The skill instructions now treat the first-use update check as a soft prerequisite before live Abel API usage.
- The update flow now checks only the installed `causal-abel` skill instead of scanning every tracked skill.
- The refresh guidance now uses a single-skill `npx skills add ... --skill causal-abel` command instead of `npx skills update`.
- The user-facing prompt is now intentionally warmer and ends with a short `Y/N` choice.

### Notes

- Update-check failures are intentionally non-blocking so the normal authorization and probing flow can continue.
