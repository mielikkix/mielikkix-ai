"""Tests for the Stage 14 accessibility analyzer
(app/services/seo_accessibility_analyzer.py) -- pure functions, no DB/
network. Every assertion traces back to a specific fake crawled-page
object, never an invented number.
"""
from types import SimpleNamespace

from app.services import seo_accessibility_analyzer as aa


def _page(**overrides):
    defaults = dict(
        url="https://greenleaf.test/",
        html_lang_present=True,
        heading_outline=[1, 2, 2, 3],
        form_inputs_missing_label=0,
        links_missing_accessible_name=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_healthy_page_has_no_findings():
    assert aa.analyze_page(_page()) == []


def test_missing_html_lang_is_low_severity():
    findings = aa.analyze_page(_page(html_lang_present=False))
    finding = next(f for f in findings if f.rule_code == "missing_html_lang")
    assert finding.severity == "low"


def test_html_lang_none_is_not_flagged():
    """None means 'couldn't assess' (a broken/non-HTML page) -- only an
    actual False is a real finding."""
    findings = aa.analyze_page(_page(html_lang_present=None))
    assert not any(f.rule_code == "missing_html_lang" for f in findings)


def test_heading_skip_is_detected():
    findings = aa.analyze_page(_page(heading_outline=[1, 2, 4]))
    finding = next(f for f in findings if f.rule_code == "heading_hierarchy_skip")
    assert finding.severity == "informational"
    assert finding.evidence == {"heading_outline": [1, 2, 4]}


def test_heading_going_back_up_is_not_a_skip():
    """h3 followed by h1 (a new top-level section) is normal document
    structure, not a hierarchy skip -- only skipping DEEPER matters."""
    findings = aa.analyze_page(_page(heading_outline=[1, 2, 3, 1, 2]))
    assert not any(f.rule_code == "heading_hierarchy_skip" for f in findings)


def test_empty_heading_outline_is_not_flagged():
    findings = aa.analyze_page(_page(heading_outline=[]))
    assert not any(f.rule_code == "heading_hierarchy_skip" for f in findings)


def test_form_inputs_missing_label_is_medium_severity():
    findings = aa.analyze_page(_page(form_inputs_missing_label=2))
    finding = next(f for f in findings if f.rule_code == "form_inputs_missing_label")
    assert finding.severity == "medium"
    assert finding.evidence == {"form_inputs_missing_label": 2}


def test_links_missing_accessible_name_is_medium_severity():
    findings = aa.analyze_page(_page(links_missing_accessible_name=1))
    finding = next(f for f in findings if f.rule_code == "links_missing_accessible_name")
    assert finding.severity == "medium"


def test_analyze_combines_findings_across_pages():
    pages = [_page(html_lang_present=False), _page(url="https://greenleaf.test/menu", form_inputs_missing_label=1)]
    findings = aa.analyze(pages)
    codes = {f.rule_code for f in findings}
    assert codes == {"missing_html_lang", "form_inputs_missing_label"}


def test_health_score_deducts_for_each_finding():
    findings = aa.analyze_page(_page(html_lang_present=False, form_inputs_missing_label=1))
    # low (-2) + medium (-5) = 93
    assert aa.health_score(findings) == 93
