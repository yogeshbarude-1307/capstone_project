"""Milestone 12 acceptance tests (docs/12): the mandatory reporting caveat
must appear verbatim in the final POC findings doc, and every non-goal from
docs/01 must be addressed in the production-gap doc."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsfs.config import REPO_ROOT

FINDINGS_DOC = REPO_ROOT / "docs" / "17-poc-findings.md"
GAP_DOC = REPO_ROOT / "docs" / "18-production-gap.md"

# Verbatim from docs/09-evaluation-plan.md — must appear in FINDINGS_DOC.
from dsfs.evaluation.report import POC_CAVEAT as MANDATORY_CAVEAT

# Every non-goal from docs/01 — a keyword that must appear in the gap doc.
NON_GOAL_KEYWORDS = [
    "Kubernetes",
    "Message bus",
    "Online/low-latency",
    "Automatic model",
    "Multi-region",
    "Real company notes",
    "Hosted/API LLMs",
    "Cloud storage",
    "Enterprise feature store",
    "Formal security",
    "Human-review workflow",
    "Production-grade cost",
]


class TestM12FindingsDoc:
    def test_findings_doc_exists(self):
        assert FINDINGS_DOC.exists(), f"Missing required doc: {FINDINGS_DOC.name}"

    def test_mandatory_caveat_present_verbatim(self):
        """docs/12 acceptance: 'the mandatory reporting caveat from docs/09 is
        present verbatim in the final POC report'."""
        raw = FINDINGS_DOC.read_text(encoding="utf-8")
        # Strip Markdown blockquote markers then collapse all whitespace so
        # line-wrapped blockquote text ("> word\n> word") still matches.
        stripped = "\n".join(
            line.lstrip("> ").rstrip() for line in raw.splitlines()
        )
        normalized_text = " ".join(stripped.split())
        normalized_caveat = " ".join(MANDATORY_CAVEAT.split())
        assert normalized_caveat in normalized_text, (
            "Mandatory caveat from docs/09-evaluation-plan.md not found verbatim "
            f"in {FINDINGS_DOC.name}. Add it to satisfy docs/12 M12 acceptance criteria."
        )

    def test_gate_table_present(self):
        """The findings doc must address the Gate A–I chain."""
        text = FINDINGS_DOC.read_text(encoding="utf-8")
        assert "Gate" in text and "Not addressed" in text, (
            "Expected a Gate A-I assessment table in findings doc."
        )

    def test_decision_logic_branch_stated(self):
        """docs/08 decision-logic branch must be explicitly named."""
        text = FINDINGS_DOC.read_text(encoding="utf-8")
        assert "B" in text and ("B ≈ A" in text or "B ≈ A" in text or "B≈A" in text or "B â‰ˆ A" in text), (
            "Expected a decision-logic branch statement (B≈A / B>A / etc.) in findings doc."
        )


class TestM12ProductionGapDoc:
    def test_gap_doc_exists(self):
        assert GAP_DOC.exists(), f"Missing required doc: {GAP_DOC.name}"

    @pytest.mark.parametrize("keyword", NON_GOAL_KEYWORDS)
    def test_non_goal_addressed(self, keyword: str):
        """docs/12 acceptance: every non-goal from docs/01 is either still
        excluded or explicitly justified as newly in-scope."""
        text = GAP_DOC.read_text(encoding="utf-8")
        assert keyword.lower() in text.lower(), (
            f"Non-goal '{keyword}' from docs/01 not addressed in {GAP_DOC.name}."
        )

    def test_no_non_goal_silently_violated(self):
        """The gap doc must contain an explicit 'no non-goal was silently
        violated' statement or equivalent."""
        text = GAP_DOC.read_text(encoding="utf-8")
        assert "non-goal" in text.lower() and "violated" in text.lower(), (
            f"Expected explicit non-goal compliance statement in {GAP_DOC.name}."
        )
