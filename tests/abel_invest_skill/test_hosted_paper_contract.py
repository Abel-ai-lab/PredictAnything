from __future__ import annotations

from ._memory_helpers import *  # noqa: F401,F403

def test_contract_report_rejects_same_source_as_asset_and_initial_state(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    source = branch / "trade-log.csv"
    source.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {
        "paths": {
            "packagedFiles": [
                {
                    "artifactPath": "strategy/assets/trade-log.csv",
                    "sourcePath": "trade-log.csv",
                    "purpose": "read-only replay input",
                }
            ],
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/trade-log.csv",
                    "sourcePath": "trade-log.csv",
                    "purpose": "incorrect duplicate state seed",
                }
            ],
        }
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="both immutable strategy asset and mutable initial state seed",
    ):
        promotion_helpers._report_packaged_files(
            report,
            branch=branch,
            is_denylisted_source=lambda path: False,
        )


def test_contract_report_rejects_research_evidence_as_live_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    evidence = branch / "promotions" / "round-001" / "trade-log.csv"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/trade-log.csv",
            source_path=evidence,
            purpose="selected round trade log",
            role="base_asset",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="generated research evidence",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            report=report,
        )


def test_contract_report_rejects_temp_generated_asset_as_live_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    generated = tmp_path / "tmp" / "hosted-paper" / "next_positions.csv"
    generated.parent.mkdir(parents=True)
    generated.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/next_positions.csv",
            source_path=generated,
            purpose="derived selected-round lookup",
            role="base_asset",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="generated research evidence",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            report=report,
        )


def test_contract_report_rejects_export_trade_log_as_live_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    destination = tmp_path / "paper-ready-artifact"
    destination.mkdir()
    generated = destination / "trade-log.csv"
    generated.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/trade-log.csv",
            source_path=generated,
            purpose="dated paper replay source",
            role="base_asset",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="generated research evidence or export output",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            destination=destination,
            report=report,
        )


def test_contract_report_allows_external_trade_log_named_asset(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    destination = tmp_path / "paper-ready-artifact"
    destination.mkdir()
    external = tmp_path / "trading-internal" / "data" / "trade-log.csv"
    external.parent.mkdir(parents=True)
    external.write_text("date,next_position\n2020-01-01,1\n", encoding="utf-8")
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="strategy/assets/trade-log.csv",
            source_path=external,
            purpose="original external signal dependency",
            role="base_asset",
        ),
    )

    promotion_helpers._validate_packaged_research_evidence_sources(
        packaged,
        branch=branch,
        destination=destination,
        report=report,
    )


def test_contract_report_rejects_oracle_answers_as_initial_state(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    state = branch / "runtime" / "initial-state" / "strategy" / "paper-seed.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps(
            {
                "schema": "paper-seed/v1",
                "seed_source": "selected_round_tail_override",
                "tail_overrides": {"2026-05-18": 0.0},
            }
        ),
        encoding="utf-8",
    )
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="runtime/initial-state/strategy/paper-seed.json",
            source_path=state,
            purpose="startup cursor seed",
            role="initial_state",
        ),
    )

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="validation oracle answers",
    ):
        promotion_helpers._validate_packaged_research_evidence_sources(
            packaged,
            branch=branch,
            report=report,
        )


def test_contract_report_allows_strategy_owned_initial_state(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    branch.mkdir()
    state = branch / "runtime" / "initial-state" / "strategy" / "paper-state.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps(
            {
                "schema": "paper-state/v1",
                "calendar_origin": "2023-03-08",
                "last_model_refit_ordinal": 800,
                "state_end": "2026-05-18",
            }
        ),
        encoding="utf-8",
    )
    report = {"paperSignal": _paper_signal()}
    packaged = (
        promotion_helpers.PromotionPackagedFile(
            artifact_path="runtime/initial-state/strategy/paper-state.json",
            source_path=state,
            purpose="strategy-owned cutover metadata",
            role="initial_state",
        ),
    )

    promotion_helpers._validate_packaged_research_evidence_sources(
        packaged,
        branch=branch,
        report=report,
    )


def test_contract_report_does_not_gate_on_live_readiness_prose() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(
            live_readiness="finite replay after the packaged log returns neutral",
        ),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )


def test_contract_report_allows_negated_replay_language() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(
            design=_paper_design(),
            live_readiness=(
                "get_paper_signal reads live feeds and persisted state for future "
                "paper days; this is not a replay of research evidence."
            ),
        ),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )


def test_contract_report_requires_paper_signal_design_contract() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": _paper_continuation(),
            "evidence": _paper_evidence(),
            "liveReadiness": "continuing paper signal from bounded live history",
        },
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="paperSignal.design",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_requires_continuation_contract() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "design": _paper_design(),
            "evidence": _paper_evidence(),
            "liveReadiness": "continuing paper signal from bounded live history",
        },
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="paperSignal.continuation",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_requires_evidence_contract() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": {
            "implemented": True,
            "incrementalReady": True,
            "continuation": _paper_continuation("stateful_continuation"),
            "design": _paper_design(uses_state=True, cutover_state_required=True),
            "liveReadiness": "continuing paper signal from bounded live history",
        },
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="paperSignal.evidence",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_allows_stateless_without_get_paper_signal() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def compute_decisions(self, ctx):\n"
        "        close = ctx.target.series('close')\n"
        "        return ctx.decisions((close > close.shift(1)).fillna(0.0))\n"
    )
    report = {
        "paperSignal": _paper_signal(method="stateless_recompute"),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )

    profile = promotion_helpers._report_paper_execution_profile(report)
    assert profile == {
        "schema": "abel.paper-execution-profile/v1",
        "history": {
            "boundary": "fixed_lookback",
            "lookbackBars": 1,
            "feeds": ["TSLA"],
            "reason": "test strategy needs a bounded paper history declaration",
        },
    }


def test_hosted_paper_request_is_actionable_for_training_like_source(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    promoted_dir = branch / "promoted"
    promoted_dir.mkdir(parents=True)
    source = promoted_dir / "engine.py"
    source.write_text("# promoted\n", encoding="utf-8")
    scan = {
        "sourceScan": {
            "positiveFindings": {"observedFitCalls": ["model.fit"]},
        },
        "paperSignal": {
            "implemented": False,
            "sourceTrainingCalls": ["model.fit"],
        },
        "backtestWindow": {
            "effectiveWindow": {"start": "2020-01-01", "end": "2020-12-31"}
        },
    }

    request_path = promotion_helpers._write_hosted_paper_contract_request(
        promoted_dir,
        branch=branch,
        source_path=source,
        dependency_scan=scan,
        signals=[
            {
                "kind": "missing_paper_signal",
                "value": "get_paper_signal",
                "reason": "missing",
            }
        ],
    )

    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert "workOrder" not in request
    assert "mission" not in request
    assert "runtimeApiFacts" not in request
    assert "reportContract" not in request
    assert "gateContract" not in request
    assert request["requirements"]["statefulContinuationRequired"] is True
    assert request["requirements"]["continuationMethod"] == "stateful_continuation"
    assert request["requirements"]["observedTrainingCalls"] == ["model.fit"]
    assert request["contractGuide"]["referencePath"] == "references/hosted-paper-contract.md"
    assert "relativePath" not in request["contractGuide"]
    assert request["facts"]["strategyProfile"]["observedTrainingCalls"] == ["model.fit"]
    assert request["facts"]["sourceScan"]["observedFitCalls"] == [
        "model.fit"
    ]
    assert request["validation"]["attemptPolicy"]["liveContractFailures"] == 0
    assert "acceptanceCriteria" not in request
    assert "agentQuestions" not in request


def test_hosted_paper_request_opens_full_replay_fallback_after_failures(
    tmp_path: Path,
) -> None:
    branch = tmp_path / "branch"
    promoted_dir = branch / "promoted"
    promoted_dir.mkdir(parents=True)
    source = promoted_dir / "engine.py"
    source.write_text("# promoted\n", encoding="utf-8")
    scan = {
        "paperSignal": {"implemented": True},
        "backtestWindow": {
            "effectiveWindow": {"start": "2020-01-01", "end": "2020-12-31"}
        },
    }
    failure = {"status": "failed", "failedGates": [{"name": "paper_dry_run"}]}

    for _ in range(3):
        request_path = promotion_helpers._write_hosted_paper_contract_request(
            promoted_dir,
            branch=branch,
            source_path=source,
            dependency_scan=scan,
            signals=[],
            validation_failure=failure,
        )

    request = json.loads(request_path.read_text(encoding="utf-8"))
    policy = request["validation"]["attemptPolicy"]
    assert policy["liveContractFailures"] == 3
    assert policy["fullReplayFallbackEligible"] is True
    assert request["requirements"]["fallback"]["status"] == "available"


def test_contract_report_rejects_full_replay_fallback_before_policy_allows() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    design = _paper_design()
    design["history"]["boundary"] = "origin_anchored"
    design["cutover"]["mode"] = "full_replay"
    report = {
        "paperSignal": _paper_signal(
            method="full_replay_fallback",
            design=design,
            live_readiness="continuing paper signal via fallback path under hosted limits",
        ),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="fullReplayFallbackEligible=true",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
        full_replay_fallback_allowed=True,
    )

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
        full_replay_fallback_allowed=True,
        source_dependency_scan={
            "sourceScan": {"positiveFindings": {"observedFitCalls": ["model.fit"]}}
        },
    )


def test_training_scan_reports_observed_calls_without_false_trainy_match() -> None:
    source = (
        "class BranchEngine:\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        train_y = self.history['target']\n"
        "        if train_y.notna().any():\n"
        "            self.model.fit(self.features, train_y)\n"
        "        return {'next_position': 1.0}\n"
    )

    facts = promotion_helpers._paper_signal_design_facts(source)

    assert facts["trainingCalls"] == ["self.model.fit"]
    assert "train_y.notna" not in facts["sourceTrainingCalls"]


def test_contract_report_rejects_stateless_recompute_with_fit_in_signal_path() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        self.model.fit(self.features, self.target)\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(method="stateless_recompute"),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="stateless_recompute conflicts with observed ML training",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_contract_report_rejects_stateless_override_for_fit_observation() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        self.model.fit(self.features, self.target)\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paperSignal": _paper_signal(method="stateless_recompute"),
        "limitations": [],
    }
    report["paperSignal"]["evidence"]["agentOverrides"] = [
        {
            "scanObservation": "source contains self.model.fit in get_paper_signal",
            "agentFinding": (
                "the fit result is unused in the returned exposure and does not affect "
                "the paper signal"
            ),
        }
    ]

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="stateful_continuation",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )


def test_trade_log_oracle_facts_withhold_expected_values(tmp_path: Path) -> None:
    trade_log = tmp_path / "trade-log.csv"
    trade_log.write_text(
        "date,next_position\n"
        "2026-05-14,0\n"
        "2026-05-15,0.35\n"
        "2026-05-18,0\n",
        encoding="utf-8",
    )

    facts = promotion_helpers._trade_log_oracle_facts(trade_log)

    assert facts["tailSample"]
    assert facts["canonicalDecisionTimeline"]["first"]["decisionIndex"] == 0
    assert facts["canonicalDecisionTimeline"]["last"]["asOf"] == "2026-05-18"
    assert all("expectedNextPosition" not in item for item in facts["tailSample"])
    assert "withheld" in facts["diagnosticPolicy"]


def test_contract_report_allows_cutover_state_without_initial_state_files() -> None:
    source = (
        "import json\n"
        "from abel_edge.engine.base import StrategyEngine\n"
        "from abel_edge.runtime_paths import context_runtime_paths\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def build_paper_initial_state(self, *, cutover_as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'cutover_as_of': str(cutover_as_of)}), encoding='utf-8')\n"
        "        return {'cutover_as_of': str(cutover_as_of)}\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        path = context_runtime_paths(self.context).state / 'strategy/paper_state.json'\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text(json.dumps({'last_as_of': str(as_of)}), encoding='utf-8')\n"
        "        return {'next_position': 1.0}\n"
    )
    report = {
        "paths": {"packagedFiles": [], "initialStateFiles": []},
        "paperSignal": _paper_signal(
            method="stateful_continuation",
            design=_paper_design(
                uses_state=True,
                cutover_state_required=True,
            ),
            live_readiness="continuing paper signal from startup state",
        ),
        "limitations": [],
    }

    promotion_helpers._validate_agent_paper_signal_contract(
        report,
        source,
        require_paper_signal=True,
    )


def test_contract_report_rejects_cutover_state_before_selected_round_end() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    design = _paper_design(
        uses_state=True,
        cutover_state_required=True,
    )
    design["cutover"]["stateEnd"] = "2020-01-02"
    report = {
        "paths": {
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/paper-state.json",
                    "sourcePath": "paper-state.json",
                }
            ]
        },
        "paperSignal": _paper_signal(
            method="stateful_continuation",
            design=design,
            live_readiness="continuing paper signal from startup state",
        ),
        "limitations": [],
    }
    candidate = Namespace(edge_result={"effective_window": {"end": "2020-12-31"}})

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="selected round cutover end 2020-12-31",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
            candidate=candidate,
        )


def test_contract_report_rejects_full_replay_cutover_mode() -> None:
    source = (
        "from abel_edge.engine.base import StrategyEngine\n"
        "class BranchEngine(StrategyEngine):\n"
        "    def get_paper_signal(self, *, as_of=None):\n"
        "        return {'next_position': 1.0}\n"
    )
    design = _paper_design(
        uses_state=True,
        cutover_state_required=True,
    )
    design["cutover"]["mode"] = "full_replay"
    report = {
        "paths": {
            "initialStateFiles": [
                {
                    "artifactPath": "runtime/initial-state/strategy/paper-state.json",
                    "sourcePath": "paper-state.json",
                }
            ]
        },
        "paperSignal": _paper_signal(
            method="stateful_continuation",
            design=design,
            live_readiness="continuing paper signal from startup state",
        ),
        "limitations": [],
    }

    with pytest.raises(
        promotion_helpers.PromotionHostedPaperContractRequired,
        match="full_replay",
    ):
        promotion_helpers._validate_agent_paper_signal_contract(
            report,
            source,
            require_paper_signal=True,
        )
