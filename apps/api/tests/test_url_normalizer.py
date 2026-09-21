"""Tests for app/services/url_normalizer.py -- Phase 1 fix for the SEO
Audit & Optimization agent's most-reported bug: https://mielikkix.ai and
https://mielikkix.ai/ being treated as two different pages.
"""
from app.services.url_normalizer import normalize_url


def test_the_reported_bug_trailing_slash_on_bare_domain():
    """The exact case reported: https://mielikkix.ai vs https://mielikkix.ai/."""
    assert normalize_url("https://mielikkix.ai") == normalize_url("https://mielikkix.ai/")


def test_trailing_slash_on_a_non_root_path():
    assert normalize_url("https://mielikkix.ai/menu") == normalize_url("https://mielikkix.ai/menu/")


def test_root_normalizes_to_bare_scheme_and_host():
    """Matches web_crawl.site_root()'s own bare scheme://host convention,
    so a root URL and site_root()'s output compare equal."""
    assert normalize_url("https://mielikkix.ai/") == "https://mielikkix.ai"


def test_http_and_https_are_equivalent():
    assert normalize_url("http://mielikkix.ai/") == normalize_url("https://mielikkix.ai/")


def test_www_and_non_www_are_equivalent():
    assert normalize_url("https://www.mielikkix.ai/") == normalize_url("https://mielikkix.ai/")


def test_host_case_is_insensitive():
    assert normalize_url("https://MielikkiX.AI/") == normalize_url("https://mielikkix.ai/")


def test_default_port_is_stripped():
    assert normalize_url("https://mielikkix.ai:443/") == normalize_url("https://mielikkix.ai/")
    assert normalize_url("http://mielikkix.ai:80/") == normalize_url("https://mielikkix.ai/")


def test_non_default_port_is_preserved():
    assert normalize_url("https://mielikkix.ai:8443/menu") != normalize_url("https://mielikkix.ai/menu")


def test_fragment_is_dropped():
    assert normalize_url("https://mielikkix.ai/menu#section-2") == normalize_url("https://mielikkix.ai/menu")


def test_index_html_suffix_is_stripped():
    assert normalize_url("https://mielikkix.ai/menu/index.html") == normalize_url("https://mielikkix.ai/menu/")
    assert normalize_url("https://mielikkix.ai/index.html") == normalize_url("https://mielikkix.ai/")


def test_index_php_and_htm_suffixes_are_stripped():
    assert normalize_url("https://mielikkix.ai/blog/index.php") == normalize_url("https://mielikkix.ai/blog")
    assert normalize_url("https://mielikkix.ai/blog/index.htm") == normalize_url("https://mielikkix.ai/blog")


def test_utm_tracking_params_are_removed():
    tagged = "https://mielikkix.ai/menu?utm_source=twitter&utm_medium=social&utm_campaign=launch"
    assert normalize_url(tagged) == normalize_url("https://mielikkix.ai/menu")


def test_fbclid_and_gclid_are_removed():
    assert normalize_url("https://mielikkix.ai/menu?fbclid=abc123") == normalize_url("https://mielikkix.ai/menu")
    assert normalize_url("https://mielikkix.ai/menu?gclid=xyz789") == normalize_url("https://mielikkix.ai/menu")


def test_non_tracking_query_params_are_preserved():
    assert normalize_url("https://mielikkix.ai/search?q=chatbot") != normalize_url("https://mielikkix.ai/search")


def test_non_tracking_query_params_are_order_independent():
    assert normalize_url("https://mielikkix.ai/search?a=1&b=2") == normalize_url("https://mielikkix.ai/search?b=2&a=1")


def test_mixing_a_tracking_and_real_param_keeps_only_the_real_one():
    assert normalize_url("https://mielikkix.ai/search?q=chatbot&utm_source=ad") == normalize_url(
        "https://mielikkix.ai/search?q=chatbot"
    )


def test_genuinely_different_pages_stay_different():
    assert normalize_url("https://mielikkix.ai/menu") != normalize_url("https://mielikkix.ai/about")


def test_already_normalized_url_is_unchanged():
    assert normalize_url("https://mielikkix.ai/menu") == "https://mielikkix.ai/menu"


def test_combined_real_world_variants_all_collapse_to_one_key():
    variants = [
        "https://mielikkix.ai",
        "https://mielikkix.ai/",
        "http://mielikkix.ai/",
        "https://www.mielikkix.ai/",
        "https://MIELIKKIX.AI/",
        "https://mielikkix.ai:443/",
        "https://mielikkix.ai/index.html",
        "https://mielikkix.ai/?utm_source=newsletter",
        "https://mielikkix.ai/#top",
    ]
    keys = {normalize_url(v) for v in variants}
    assert len(keys) == 1
