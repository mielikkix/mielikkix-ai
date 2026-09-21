"""Tests for the Stage 13 structured data analyzer
(app/services/seo_structured_data_analyzer.py) -- pure functions, no DB/
network. Every assertion traces back to a specific fake crawled-page
object, never an invented number.
"""
from types import SimpleNamespace

from app.services import seo_structured_data_analyzer as sda


def _page(**overrides):
    defaults = dict(
        url="https://greenleaf.test/",
        structured_data_types=["Organization"],
        structured_data_invalid_count=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_valid_structured_data_has_no_finding():
    findings = sda.analyze_page(_page())
    assert findings == []


def test_invalid_json_ld_is_medium_severity():
    findings = sda.analyze_page(_page(structured_data_invalid_count=1))
    finding = next(f for f in findings if f.rule_code == "structured_data_invalid_json")
    assert finding.severity == "medium"
    assert finding.evidence == {"structured_data_invalid_count": 1}


def test_no_finding_per_page_for_simply_having_none():
    """A single page having no structured data isn't flagged per-page --
    only the sitewide absence check (analyze(), not analyze_page()) reports
    that, once, for the whole audit -- see analyze()'s own docstring."""
    findings = sda.analyze_page(_page(structured_data_types=[], structured_data_invalid_count=0))
    assert findings == []


def test_analyze_flags_sitewide_absence_when_no_page_has_any():
    pages = [_page(structured_data_types=[]), _page(url="https://greenleaf.test/menu", structured_data_types=[])]
    findings = sda.analyze(pages)
    assert any(f.rule_code == "no_structured_data_sitewide" for f in findings)
    # Sitewide, not per-page -- exactly one finding regardless of page count.
    assert sum(1 for f in findings if f.rule_code == "no_structured_data_sitewide") == 1


def test_analyze_does_not_flag_sitewide_absence_if_any_page_has_structured_data():
    pages = [_page(structured_data_types=["Organization"]), _page(url="https://greenleaf.test/menu", structured_data_types=[])]
    findings = sda.analyze(pages)
    assert not any(f.rule_code == "no_structured_data_sitewide" for f in findings)


def test_analyze_with_no_pages_does_not_flag_sitewide_absence():
    """An audit that crawled nothing (e.g. a fully-blocked site) already
    has other findings explaining that -- don't pile on a redundant
    structured-data finding for a site with zero real data."""
    findings = sda.analyze([])
    assert findings == []


def test_analyze_combines_per_page_and_sitewide_findings():
    pages = [_page(structured_data_types=[], structured_data_invalid_count=1)]
    findings = sda.analyze(pages)
    codes = {f.rule_code for f in findings}
    assert codes == {"structured_data_invalid_json", "no_structured_data_sitewide"}


def test_health_score_deducts_for_invalid_json_finding():
    findings = sda.analyze_page(_page(structured_data_invalid_count=1))
    assert sda.health_score(findings) == 95  # medium severity = -5

    assert sda.health_score([]) == 100
