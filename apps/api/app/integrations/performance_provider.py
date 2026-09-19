"""PerformanceProvider -- abstraction around Core Web Vitals measurement,
so the SEO Audit & Optimization agent's performance pass (Stage 8, see
apps/agents/seo-copywriter/CLAUDE.md) isn't tightly coupled to Google
PageSpeed Insights specifically. Same idiom app/integrations/
calendar_provider.py and app/rag/providers/ already use: an ABC + a
get_performance_provider() factory, so swapping providers later is a
factory change, not a rewrite (root CLAUDE.md convention #6).

Every method returns None (never a fabricated number) when a real
measurement isn't available -- no API key configured, the request failed,
or that specific metric has no data for this URL. Callers must render a
None field as "Not measured", exactly this agent's CLAUDE.md's own rule:
"If real measurement is unavailable, clearly label the result... rather
than generating an estimate."
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from ..core.config import settings

PAGESPEED_STRATEGIES = ("mobile", "desktop")


@dataclass
class PerformanceMetrics:
    strategy: str  # "mobile" | "desktop"
    performance_score: Optional[int]  # Lighthouse's own 0-100 lab score
    lcp_ms: Optional[int]  # Largest Contentful Paint, lab-measured
    cls: Optional[float]  # Cumulative Layout Shift, lab-measured
    # Interaction to Next Paint -- ONLY ever from real-user CrUX field data
    # (Chrome UX Report), never a lab proxy substituted under this name.
    # Most sites, especially lower-traffic ones, won't have enough field
    # data for Google to report this -- that's an honest None, not a bug.
    inp_ms: Optional[int]
    # Total Blocking Time -- the lab-measured proxy for responsiveness,
    # always available when the lab run itself succeeds. Kept as its own
    # field, deliberately never relabeled as INP (a related but different
    # metric) -- see this class's own note above.
    tbt_ms: Optional[int]


class PerformanceProvider(ABC):
    @abstractmethod
    async def measure(self, url: str, strategy: str) -> Optional[PerformanceMetrics]:
        """Returns None if no real measurement could be obtained at all
        (no API key, request failed, rate-limited) -- the caller then
        skips storing anything for this strategy rather than guessing."""


class GooglePageSpeedProvider(PerformanceProvider):
    """Google's free PageSpeed Insights v5 API -- no OAuth, just an API key
    on a Google Cloud project with the PageSpeed Insights API enabled (see
    .env.example's GOOGLE_PAGESPEED_API_KEY comment for the setup link)."""

    _ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

    async def measure(self, url: str, strategy: str) -> Optional[PerformanceMetrics]:
        if not settings.google_pagespeed_api_key:
            return None
        if strategy not in PAGESPEED_STRATEGIES:
            raise ValueError(f"strategy must be one of {PAGESPEED_STRATEGIES}")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    self._ENDPOINT,
                    params={
                        "url": url,
                        "key": settings.google_pagespeed_api_key,
                        "strategy": strategy,
                        "category": "performance",
                    },
                )
            if resp.status_code >= 400:
                return None
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        lighthouse = data.get("lighthouseResult") or {}
        categories = lighthouse.get("categories") or {}
        audits = lighthouse.get("audits") or {}

        performance_category = categories.get("performance") or {}
        raw_score = performance_category.get("score")
        performance_score = round(raw_score * 100) if isinstance(raw_score, (int, float)) else None

        lcp_raw = (audits.get("largest-contentful-paint") or {}).get("numericValue")
        lcp_ms = round(lcp_raw) if isinstance(lcp_raw, (int, float)) else None

        cls_raw = (audits.get("cumulative-layout-shift") or {}).get("numericValue")
        cls = round(cls_raw, 3) if isinstance(cls_raw, (int, float)) else None

        tbt_raw = (audits.get("total-blocking-time") or {}).get("numericValue")
        tbt_ms = round(tbt_raw) if isinstance(tbt_raw, (int, float)) else None

        # Real-user field data (Chrome UX Report), when Google has enough
        # of it for this exact origin -- absent for most lower-traffic
        # sites, which is why this stays a separate, often-null field
        # rather than something every audit is expected to have.
        field_metrics = (data.get("loadingExperience") or {}).get("metrics") or {}
        inp_percentile = (field_metrics.get("INTERACTION_TO_NEXT_PAINT") or {}).get("percentile")
        inp_ms = round(inp_percentile) if isinstance(inp_percentile, (int, float)) else None

        return PerformanceMetrics(
            strategy=strategy,
            performance_score=performance_score,
            lcp_ms=lcp_ms,
            cls=cls,
            inp_ms=inp_ms,
            tbt_ms=tbt_ms,
        )


def get_performance_provider() -> PerformanceProvider:
    """Only one implementation exists today (Google PageSpeed Insights) --
    this factory is the seam a future provider (e.g. a self-run Lighthouse
    CI, WebPageTest) plugs into without seo_audit_service.py's own code
    changing at all, the same role get_calendar_provider() plays for
    calendars and get_llm_provider() plays for LLM providers."""
    return GooglePageSpeedProvider()
