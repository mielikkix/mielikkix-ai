"""Shared finding/scoring types for the SEO Audit & Optimization agent's
analyzers (technical, on-page, ...) -- see apps/agents/seo-audit/
CLAUDE.md. One FindingDraft/health_score implementation so every analyzer
stage scores findings identically instead of each reinventing it.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SEVERITY_WEIGHTS = {"critical": 20, "high": 10, "medium": 5, "low": 2, "informational": 0}


@dataclass
class FindingDraft:
    category: str
    rule_code: str
    severity: str
    issue: str
    affected_url: Optional[str] = None
    explanation: Optional[str] = None
    recommended_fix: Optional[str] = None
    evidence: Dict = field(default_factory=dict)


def health_score(findings: List[FindingDraft]) -> int:
    """0-100, starting from 100 and deducting per finding by severity --
    an internal diagnostic score based on this agent's own checks, never
    presented as an actual Google ranking signal (this agent's CLAUDE.md,
    Phase 10)."""
    score = 100
    for f in findings:
        score -= SEVERITY_WEIGHTS.get(f.severity, 0)
    return max(0, min(100, score))
