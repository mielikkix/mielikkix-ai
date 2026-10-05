import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Check, X, Trash2, Globe, PlayCircle, Star } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { AgentGate } from '../../shared/components/AgentGate'
import { useAgentAccess, useAgentCatalog, AgentTier } from '../../shared/hooks/usePlan'
import { useCurrency } from '../../shared/hooks/useCurrency'
import { CurrencySwitcher } from '../components/CurrencySwitcher'
import { useT, type MessageKey } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

interface SeoWebsite {
  id: string
  url: string
  name: string | null
  target_country: string | null
  target_language: string | null
  primary_category: string | null
  target_keywords: string[]
  crawl_tier: 'starter' | 'standard' | 'advanced'
  // Stage 15 (recurring audits) -- null means no schedule, the default.
  audit_schedule: 'weekly' | 'monthly' | null
  next_scheduled_audit_at: string | null
  created_at: string
}

interface SeoGoogleStatus {
  connected: boolean
  google_account_email: string | null
  analytics_property_id: string | null
  search_console_site_url: string | null
}

type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'

interface SeoAudit {
  id: string
  website_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  pages_discovered: number
  pages_crawled: number
  pages_in_sitemap?: number | null
  pages_blocked: number
  health_technical: number | null
  health_on_page: number | null
  health_performance: number | null
  health_content: number | null
  health_internal_linking: number | null
  overall_health: number | null
  finding_counts: Record<Severity, number>
  executive_summary: string | null
  created_at: string
}

interface ActionPlanItem {
  priority: number
  category: string
  rule_code: string
  issue: string
  affected_urls: string[]
  why_it_matters: string | null
  recommended_action: string | null
  expected_benefit: string
  implementation_difficulty: string
  status: string
  // Stage 12 (Google Analytics + Search Console) -- real sessions + clicks
  // summed across this item's own affected URLs, from whichever of them
  // actually had data. null means none of this item's affected URLs have
  // any real traffic data (Google not connected, or genuinely no data
  // yet) -- never a fabricated 0. Only ever used to break ties within the
  // same priority tier server-side; shown here just as a visible signal
  // of why an item sorted where it did.
  traffic_weight: number | null
}

// Phase 2 fix: these must match seo_recommendation_service.py's actual
// SEVERITY_TO_PRIORITY mapping ({"critical": 1, "high": 1, "medium": 2,
// "low": 3, "informational": 3}) exactly -- the labels here previously
// claimed Priority 2 was "High" and Priority 3 was "Medium & Below", which
// didn't match reality (High actually sorts into Priority 1, Medium into
// Priority 2). That's what produced the confusing "Priority 1 — Critical"
// heading over a group that was mostly High-severity items while the
// summary correctly said "Critical: 0" -- one real source of truth
// (SeoFinding.severity), but a wrong label describing it. If that backend
// mapping ever changes, update this to match -- don't let it drift again.
const PRIORITY_LABELS: Record<number, MessageKey> = {
  1: 'seo.priorities.p1',
  2: 'seo.priorities.p2',
  3: 'seo.priorities.p3',
}

// Phase 2 fix: health_content and health_internal_linking are removed from
// this list entirely -- verified by inspection (ARCHITECTURE-NOTES.md) that
// NO analyzer anywhere in the backend ever sets them; they are permanently
// null, for every audit, not just this one. Showing a tile that will never
// populate looks like a data problem, not a "feature not built yet"
// statement, which undermines trust in the categories that DO work.
// Performance stays -- it's a real, already-built analyzer (Stage 8) that's
// simply unconfigured in this environment (no GOOGLE_PAGESPEED_API_KEY), a
// transient gap, not a permanent one; see the "How is this calculated?"
// note below for how that distinction is explained in the UI.
const HEALTH_CATEGORIES: { key: keyof SeoAudit; label: MessageKey }[] = [
  { key: 'health_technical', label: 'seo.categories.technical' },
  { key: 'health_on_page', label: 'seo.categories.onPage' },
  { key: 'health_performance', label: 'seo.categories.performance' },
]

// Severity codes come from the API; labels are seo.severities.<code>.
const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'informational']

interface SeoFinding {
  id: string
  audit_id: string
  category: string
  rule_code: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'informational'
  affected_url: string | null
  issue: string
  explanation: string | null
  recommended_fix: string | null
  status: 'open' | 'in_progress' | 'approved' | 'completed' | 'ignored'
}

// Stage 7 of the SEO Audit & Optimization upgrade -- which finding types
// the Copywriter can generate a fix for (see app/services/seo_service.py's
// _TITLE_RULE_CODES/_META_RULE_CODES/_CONTENT_RULE_CODES). Deliberately NOT
// every rule_code: images_missing_alt has no per-image data to generate
// real alt text from, and duplicate_title/duplicate_content need a human
// choosing which page keeps which copy -- see UnsupportedFindingError.
const COPYWRITER_RULE_CODES = new Set([
  'missing_title', 'title_too_long', 'title_too_short',
  'missing_meta_description', 'meta_description_too_long', 'meta_description_too_short',
  'thin_content',
])

const AUDIT_STATUS_COLORS: Record<SeoAudit['status'], string> = {
  pending: 'bg-slate-100 text-slate-600',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
}

const SEVERITY_COLORS: Record<SeoFinding['severity'], string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-slate-100 text-slate-600',
  informational: 'bg-blue-50 text-blue-600',
}

// Stage 5 of the SEO Audit & Optimization upgrade -- the audit's overall
// diagnostic score, per-category breakdown, and findings-by-severity
// counts, each clickable to drill into that severity's findings below.
// Explicitly labeled as an internal score, never a real Google ranking
// signal (see apps/agents/seo-audit/CLAUDE.md, Phase 10).
interface SeoPerformanceMeasurement {
  strategy: 'mobile' | 'desktop'
  performance_score: number | null
  lcp_ms: number | null
  cls_score: number | null
  inp_ms: number | null
  tbt_ms: number | null
}

// Stage 8 of the SEO Audit & Optimization upgrade -- real Core Web Vitals
// (Google PageSpeed Insights), one row per strategy that actually got a
// measurement. Renders nothing if the list is empty ("Not measured" is
// already implied by the Performance tile above showing "—") -- never a
// fabricated number, per this agent's CLAUDE.md.
function CoreWebVitals({ auditId }: { auditId: string }) {
  const { t, tCode, formatNumber } = useT()
  const { data: measurements = [] } = useQuery<SeoPerformanceMeasurement[]>({
    queryKey: ['seo', 'performance', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/performance`).then((r) => r.data),
  })

  if (measurements.length === 0) return null

  return (
    <div className="flex flex-wrap gap-4 rounded-lg bg-white p-3 text-sm border border-slate-200">
      {measurements.map((m) => (
        <div key={m.strategy}>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{tCode('seo.vitals.strategies', m.strategy)}</p>
          <p className="text-slate-600">
            {m.performance_score !== null ? t('seo.vitals.score', { score: m.performance_score }) : t('seo.vitals.scoreMissing')}
            {m.lcp_ms !== null && ` · LCP: ${formatNumber(m.lcp_ms / 1000, 1)} s`}
            {m.cls_score !== null && ` · CLS: ${formatNumber(m.cls_score, 3)}`}
            {m.inp_ms !== null ? ` · INP: ${formatNumber(m.inp_ms)} ms` : m.tbt_ms !== null ? ` · TBT: ${formatNumber(m.tbt_ms)} ms` : ''}
          </p>
        </div>
      ))}
    </div>
  )
}

function SeoHealthPanel({ audit, severityFilter, onSeverityFilter }: {
  audit: SeoAudit
  severityFilter: Severity | null
  onSeverityFilter: (s: Severity | null) => void
}) {
  const { t } = useT()
  return (
    <div className="mt-4 space-y-3 rounded-lg bg-slate-50 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-500">
            {t('seo.health.label')} <span className="text-xs text-slate-400">{t('seo.health.note')}</span>
          </p>
          <p className="text-3xl font-bold text-slate-900">
            {audit.overall_health !== null ? `${audit.overall_health}/100` : '—'}
          </p>
          <details className="mt-1 text-xs text-slate-400 print:hidden">
            <summary className="cursor-pointer select-none underline decoration-dotted">
              {t('seo.health.how')}
            </summary>
            <p className="mt-1 max-w-xs text-slate-500">{t('seo.health.howText')}</p>
          </details>
        </div>
        <div className="flex gap-4">
          {HEALTH_CATEGORIES.map(({ key, label }) => (
            <div key={key} className="text-center">
              <p className="text-lg font-semibold text-slate-700">
                {audit[key] !== null ? (audit[key] as number) : '—'}
              </p>
              <p className="text-xs text-slate-400">{t(label)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 print:hidden">
        {SEVERITIES.map((severity) => (
          <button
            key={severity}
            aria-pressed={severityFilter === severity}
            onClick={() => onSeverityFilter(severityFilter === severity ? null : severity)}
            className={clsx(
              'rounded-full px-3 py-1 text-sm font-medium transition-colors',
              severityFilter === severity ? SEVERITY_COLORS[severity] : 'bg-white text-slate-500 border border-slate-200',
            )}
          >
            {t(`seo.severities.${severity}`)}: {audit.finding_counts[severity]}
          </button>
        ))}
      </div>
      {/* Print-only static equivalent of the interactive filter buttons above
          -- the numbers are useful in a printed report, the click-to-filter
          behavior isn't. */}
      <div className="hidden flex-wrap gap-3 text-sm print:flex">
        {SEVERITIES
          .filter((s) => audit.finding_counts[s] > 0)
          .map((severity) => (
            <span key={severity} className="rounded-full border border-slate-300 px-3 py-1">
              {t(`seo.severities.${severity}`)}: {audit.finding_counts[severity]}
            </span>
          ))}
      </div>

      {audit.executive_summary && (
        <p className="rounded-lg bg-white p-3 text-sm text-slate-700 border border-slate-200">
          {audit.executive_summary}
        </p>
      )}

      <CoreWebVitals auditId={audit.id} />
    </div>
  )
}

// Stage 6 of the SEO Audit & Optimization upgrade -- the deterministic,
// prioritized action plan (see app/services/seo_recommendation_service.py):
// one item per distinct issue type, grouping every affected URL under it.
function ActionPlanList({ auditId }: { auditId: string }) {
  const { t, formatNumber } = useT()
  const { data: items = [], isLoading } = useQuery<ActionPlanItem[]>({
    queryKey: ['seo', 'action-plan', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/action-plan`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-400">{t('seo.plan.loading')}</p>
  if (items.length === 0) return <p className="text-sm text-slate-400">{t('seo.plan.empty')}</p>

  const byPriority = new Map<number, ActionPlanItem[]>()
  for (const item of items) {
    byPriority.set(item.priority, [...(byPriority.get(item.priority) ?? []), item])
  }

  return (
    <div className="space-y-4">
      {[1, 2, 3].map((priority) => {
        const group = byPriority.get(priority)
        if (!group || group.length === 0) return null
        return (
          <div key={priority}>
            <h4 className="mb-2 text-sm font-semibold text-slate-700">{t(PRIORITY_LABELS[priority])}</h4>
            <div className="space-y-2">
              {group.map((item) => (
                <div key={item.rule_code} className={clsx('rounded-lg border px-3 py-2 print:break-inside-avoid', item.status === 'ignored' && 'opacity-50')}>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-slate-800">{item.issue}</p>
                    {/* Stage 12 (Google Analytics + Search Console) -- only
                        rendered when at least one of this item's affected
                        URLs has real data; null (not 0) means none do, e.g.
                        Google isn't connected, so no badge at all rather
                        than a misleading "0". */}
                    {item.traffic_weight !== null && (
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                        {t('seo.plan.traffic', { count: formatNumber(item.traffic_weight) })}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-slate-500">
                    {t('seo.plan.meta', {
                      pages: item.affected_urls.length,
                      difficulty: item.implementation_difficulty,
                      benefit: item.expected_benefit,
                    })}
                  </p>
                  {item.recommended_action && <p className="mt-1 text-sm text-slate-700">{t('seo.plan.fix', { fix: item.recommended_action })}</p>}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface SeoAuditReport {
  website_id: string
  website_url: string
  website_name: string | null
  audit_id: string
  audit_completed_at: string | null
  overall_health: number | null
  executive_summary: string | null
  finding_counts: Record<Severity, number>
  top_action_items: ActionPlanItem[]
  keyword_opportunity_count: number
}

// Stage 11 of the SEO Audit & Optimization upgrade -- a single client-
// presentable rollup of one completed audit (see app/services/
// seo_report_service.py). No new analysis here, just an assembly of data
// already computed by earlier stages. PDF export is deliberately NOT
// implemented (see this agent's CLAUDE.md, Phase 17) -- "Print / Save as
// PDF" below is the browser's own native print dialog, not a generated PDF.
function ReportView({ auditId }: { auditId: string }) {
  const { t, formatDate, formatNumber } = useT()
  const { data: report, isLoading, isError } = useQuery<SeoAuditReport>({
    queryKey: ['seo', 'report', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/report`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-400">{t('seo.report.loading')}</p>
  if (isError || !report) {
    return <p className="text-sm text-red-500">{t('seo.report.unavailable')}</p>
  }

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 print:border-0 print:p-0">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">{t('seo.report.title', { name: report.website_name || report.website_url })}</h3>
        <p className="text-sm text-slate-500">
          {report.website_url}
          {report.audit_completed_at && ` · ${t('seo.report.generated', { date: formatDate(report.audit_completed_at) })}`}
        </p>
      </div>

      <div className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 print:border print:border-slate-300">
        <span className="text-2xl font-bold text-slate-900">{report.overall_health ?? '—'}</span>
        <span className="text-sm text-slate-500">{t('seo.report.overall')}</span>
      </div>

      {report.executive_summary && (
        <div>
          <h4 className="mb-1 text-sm font-semibold text-slate-700">{t('seo.report.summary')}</h4>
          <p className="text-sm text-slate-700">{report.executive_summary}</p>
        </div>
      )}

      <div>
        <h4 className="mb-1 text-sm font-semibold text-slate-700">{t('seo.report.issues')}</h4>
        <div className="flex flex-wrap gap-3 text-sm">
          {(Object.keys(report.finding_counts) as Severity[])
            .filter((s) => report.finding_counts[s] > 0)
            .map((severity) => (
              <span key={severity} className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
                {report.finding_counts[severity]} {t(`seo.severities.${severity}`)}
              </span>
            ))}
          {Object.values(report.finding_counts).every((c) => c === 0) && (
            <span className="text-slate-400">{t('seo.report.noIssues')}</span>
          )}
        </div>
      </div>

      {report.top_action_items.length > 0 && (
        <div>
          <h4 className="mb-1 text-sm font-semibold text-slate-700">{t('seo.report.top')}</h4>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
            {report.top_action_items.map((item) => (
              <li key={item.rule_code}>
                {t('seo.report.topItem', {
                  issue: item.issue,
                  pages: item.affected_urls.length,
                  difficulty: item.implementation_difficulty,
                })}
                {item.traffic_weight !== null && ` — ${t('seo.plan.traffic', { count: formatNumber(item.traffic_weight) })}`}
              </li>
            ))}
          </ol>
        </div>
      )}

      <p className="text-sm text-slate-500">{t('seo.report.keywords', { count: report.keyword_opportunity_count })}</p>
    </div>
  )
}

interface ComparisonFinding {
  category: string
  rule_code: string
  severity: string
  affected_url: string | null
  issue: string
}

interface SeoAuditComparison {
  previous_audit_id: string
  current_audit_id: string
  previous_created_at: string
  current_created_at: string
  overall_health_previous: number | null
  overall_health_current: number | null
  overall_health_delta: number | null
  finding_counts_previous: Record<Severity, number>
  finding_counts_current: Record<Severity, number>
  resolved_findings: ComparisonFinding[]
  new_findings: ComparisonFinding[]
  persisting_findings: ComparisonFinding[]
}

// Stage 10 of the SEO Audit & Optimization upgrade -- diffs two audits of
// the same website (see app/services/seo_audit_comparison_service.py).
// Findings are matched across runs by (rule_code, affected_url), not by
// row ID, since every audit persists brand-new SeoFinding rows.
function AuditComparisonPanel({ currentAuditId, previousAuditId }: { currentAuditId: string; previousAuditId: string }) {
  const { t } = useT()
  const { data, isLoading, isError } = useQuery<SeoAuditComparison>({
    queryKey: ['seo', 'compare', currentAuditId, previousAuditId],
    queryFn: () =>
      api
        .get(`/agents/seo/audits/${currentAuditId}/compare`, { params: { against: previousAuditId } })
        .then((r) => r.data),
  })

  if (isLoading) return <p className="mt-2 text-sm text-slate-400">{t('seo.compare.loading')}</p>
  if (isError || !data) return <p className="mt-2 text-sm text-red-500">{t('seo.compare.failed')}</p>

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
      <p className="font-medium text-slate-700">
        {t('seo.compare.overall', { previous: data.overall_health_previous ?? '—', current: data.overall_health_current ?? '—' })}
        {data.overall_health_delta !== null && (
          <span className={clsx('ml-2 font-semibold', data.overall_health_delta >= 0 ? 'text-green-600' : 'text-red-600')}>
            ({data.overall_health_delta >= 0 ? '+' : ''}
            {data.overall_health_delta})
          </span>
        )}
      </p>
      <div className="flex gap-4">
        <span className="text-green-700">{t('seo.compare.resolvedCount', { count: data.resolved_findings.length })}</span>
        <span className="text-amber-700">{t('seo.compare.newCount', { count: data.new_findings.length })}</span>
        <span className="text-slate-500">{t('seo.compare.openCount', { count: data.persisting_findings.length })}</span>
      </div>
      {data.resolved_findings.length > 0 && (
        <div>
          <p className="font-medium text-slate-600">{t('seo.compare.resolved')}</p>
          <ul className="list-disc pl-5 text-slate-600">
            {data.resolved_findings.map((f) => (
              <li key={`${f.rule_code}-${f.affected_url ?? ''}`}>
                {f.issue}
                {f.affected_url && ` — ${f.affected_url}`}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.new_findings.length > 0 && (
        <div>
          <p className="font-medium text-slate-600">{t('seo.compare.new')}</p>
          <ul className="list-disc pl-5 text-slate-600">
            {data.new_findings.map((f) => (
              <li key={`${f.rule_code}-${f.affected_url ?? ''}`}>
                {f.issue}
                {f.affected_url && ` — ${f.affected_url}`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function AuditHistoryList({ audits }: { audits: SeoAudit[] }) {
  const [comparingId, setComparingId] = useState<string | null>(null)
  const { t, formatDateTime } = useT()
  const completed = audits.filter((a) => a.status === 'completed')

  if (completed.length === 0) return <p className="text-sm text-slate-400">{t('seo.history.empty')}</p>

  return (
    <div className="space-y-2">
      {completed.map((audit, i) => {
        const previous = completed[i + 1]
        return (
          <div key={audit.id} className="rounded-lg border border-slate-200 px-3 py-2 print:break-inside-avoid">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-medium text-slate-800">{formatDateTime(audit.created_at)}</p>
                <p className="text-sm text-slate-500">
                  {t('seo.history.overall', { score: audit.overall_health ?? t('seo.history.notScored') })}
                </p>
              </div>
              {previous && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="print:hidden"
                  onClick={() => setComparingId((v) => (v === audit.id ? null : audit.id))}
                >
                  {comparingId === audit.id ? t('seo.history.hide') : t('seo.history.compare')}
                </Button>
              )}
            </div>
            {previous && comparingId === audit.id && (
              <AuditComparisonPanel currentAuditId={audit.id} previousAuditId={previous.id} />
            )}
          </div>
        )
      })}
    </div>
  )
}

interface SeoKeywordOpportunity {
  id: string
  keyword: string
  intent: string | null
  suggested_page: string | null
  current_page: string | null
  content_gap: string | null
  recommendation: string | null
  volume: string
}

// Stage 9 of the SEO Audit & Optimization upgrade -- LLM-suggested keyword
// ideas grounded in this audit's own crawled pages (see app/services/
// seo_keyword_service.py). volume is always "Not available" -- no real
// search-volume/CPC/competition data source is connected, and this is
// shown honestly rather than guessed.
function KeywordOpportunitiesList({ auditId }: { auditId: string }) {
  const { t } = useT()
  const { data: keywords = [], isLoading } = useQuery<SeoKeywordOpportunity[]>({
    queryKey: ['seo', 'keyword-opportunities', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/keyword-opportunities`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-400">{t('seo.keywords.loading')}</p>
  if (keywords.length === 0) return <p className="text-sm text-slate-400">{t('seo.keywords.empty')}</p>

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-400">
        {t('seo.keywords.volumeBefore')}
        <span className="font-medium">{t('seo.keywords.volumeNA')}</span>
        {t('seo.keywords.volumeAfter')}
      </p>
      {keywords.map((k) => (
        <div key={k.id} className="rounded-lg border border-slate-200 px-3 py-2 print:break-inside-avoid">
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-800">{k.keyword}</span>
            {k.intent && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{k.intent}</span>}
          </div>
          {k.content_gap && <p className="mt-1 text-sm text-amber-700">{t('seo.keywords.gap', { gap: k.content_gap })}</p>}
          {k.current_page && <p className="mt-1 text-sm text-slate-500">{t('seo.keywords.covered', { page: k.current_page })}</p>}
          {k.suggested_page && !k.current_page && (
            <p className="mt-1 text-sm text-slate-500">{t('seo.keywords.suggested', { page: k.suggested_page })}</p>
          )}
          {k.recommendation && <p className="mt-1 text-sm text-slate-700">{k.recommendation}</p>}
        </div>
      ))}
    </div>
  )
}

// Stage 7 of the SEO Audit & Optimization upgrade -- lets the Copywriter
// generate a fix (title/meta description/content suggestion) targeted at
// one specific finding, review it, and approve or reject it, all inline.
// No live page for us to publish onto (a crawled page usually isn't a
// Product row we own) -- "Approve" just marks the draft ready for the
// business to use themselves, see seo_service.approve_draft's own docstring.
function FindingDraftAction({ finding }: { finding: SeoFinding }) {
  const qc = useQueryClient()
  const { t } = useT()
  const draftsKey = ['seo', 'finding-drafts', finding.id]
  const { data: drafts = [] } = useQuery<SeoDraft[]>({
    queryKey: draftsKey,
    queryFn: () => api.get(`/agents/seo/findings/${finding.id}/drafts`).then((r) => r.data),
  })
  const latest = drafts[0]

  const generateMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/findings/${finding.id}/generate-draft`),
    onSuccess: () => qc.invalidateQueries({ queryKey: draftsKey }),
  })
  const approveMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/drafts/${latest?.id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: draftsKey }),
  })
  const rejectMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/drafts/${latest?.id}/reject`),
    onSuccess: () => qc.invalidateQueries({ queryKey: draftsKey }),
  })

  const draftText = latest?.draft_seo_title || latest?.draft_meta_description || latest?.draft_description

  if (!latest || latest.status === 'rejected') {
    return (
      <div className="mt-2 print:hidden">
        <Button size="sm" variant="secondary" loading={generateMut.isPending} onClick={() => generateMut.mutate()}>
          <Sparkles size={14} className="mr-1" />
          {latest?.status === 'rejected' ? t('seo.draft.regenerate') : t('seo.draft.generate')}
        </Button>
        {generateMut.isError && <p role="alert" className="mt-1 text-sm text-red-600">{apiErrorMessage(generateMut.error, 'seo.draft.failed')}</p>}
      </div>
    )
  }

  return (
    <div className="mt-2 rounded-lg bg-brand-50 border border-brand-100 px-3 py-2 print:border-slate-300 print:bg-transparent">
      <p className="text-xs font-medium uppercase tracking-wide text-brand-600">{t('seo.draft.suggested')}</p>
      <p className="mt-1 text-sm text-slate-800">{draftText}</p>
      {latest.status === 'draft' ? (
        <div className="mt-2 flex gap-2 print:hidden">
          <Button size="sm" loading={approveMut.isPending} onClick={() => approveMut.mutate()}>
            <Check size={14} className="mr-1" />
            {t('seo.draft.approve')}
          </Button>
          <Button size="sm" variant="secondary" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
            <X size={14} className="mr-1" />
            {t('seo.draft.reject')}
          </Button>
        </div>
      ) : (
        <p className="mt-1 text-xs font-medium text-emerald-600">{t('seo.draft.approved')}</p>
      )}
    </div>
  )
}

// Stage 3/4 of the SEO Audit & Optimization upgrade -- the technical/
// on-page analyzers' findings for one completed audit, optionally filtered
// by severity (drilled into from SeoHealthPanel above). Recommendations/
// priority narrative are a later stage; this is the raw, real finding list.
function FindingsList({ auditId, severityFilter }: { auditId: string; severityFilter: Severity | null }) {
  const qc = useQueryClient()
  const { t } = useT()
  const { data: findings = [], isLoading } = useQuery<SeoFinding[]>({
    queryKey: ['seo', 'findings', auditId, severityFilter],
    queryFn: () =>
      api
        .get(`/agents/seo/audits/${auditId}/findings`, { params: severityFilter ? { severity: severityFilter } : {} })
        .then((r) => r.data),
  })

  const ignoreMut = useMutation({
    mutationFn: (findingId: string) => api.patch(`/agents/seo/findings/${findingId}`, { status: 'ignored' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo', 'findings', auditId] }),
  })

  if (isLoading) return <p className="text-sm text-slate-400">{t('seo.findings.loading')}</p>
  if (findings.length === 0) {
    return (
      <p className="text-sm text-slate-400">
        {severityFilter
          ? t('seo.findings.noneOfSeverity', { severity: t(`seo.severities.${severityFilter}`).toLocaleLowerCase() })
          : t('seo.findings.none')}
      </p>
    )
  }

  return (
    <div className="space-y-2">
      {findings.map((f) => (
        <div key={f.id} className={clsx('rounded-lg border px-3 py-2 print:break-inside-avoid', f.status === 'ignored' ? 'opacity-50 border-slate-100' : 'border-slate-200')}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className={clsx('mr-2 rounded-full px-2 py-0.5 text-xs font-medium uppercase', SEVERITY_COLORS[f.severity])}>
                {t(`seo.severities.${f.severity}`)}
              </span>
              <span className="font-medium text-slate-800">{f.issue}</span>
              {f.affected_url && <p className="mt-1 text-sm text-slate-500 break-all">{f.affected_url}</p>}
              {f.explanation && <p className="mt-1 text-sm text-slate-500">{f.explanation}</p>}
              {f.recommended_fix && <p className="mt-1 text-sm text-slate-700">{t('seo.findings.fix', { fix: f.recommended_fix })}</p>}
              {f.status !== 'ignored' && COPYWRITER_RULE_CODES.has(f.rule_code) && <FindingDraftAction finding={f} />}
            </div>
            {f.status !== 'ignored' && (
              <Button size="sm" variant="ghost" className="print:hidden" loading={ignoreMut.isPending} onClick={() => ignoreMut.mutate(f.id)}>
                {t('seo.findings.ignore')}
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// Combines every detail tab (Report, Action Plan, All Findings, Keyword
// Ideas, History) into one flowing document for printing/PDF export. The
// browser's native print dialog only ever captures whatever's currently
// on screen, and the on-screen UI deliberately shows one tab at a time --
// this component exists purely so "Print Full Report (PDF)" produces a
// complete document regardless of which tab happens to be selected.
// Invisible on screen (`hidden`), shown only for print (`print:block`).
// Reuses the exact same data-fetching components as the interactive tabs
// (ActionPlanList, FindingsList, etc.) rather than re-implementing their
// rendering -- their own interactive-only buttons (Ignore, Generate fix,
// Compare to previous) are individually print:hidden at their own
// definitions above, so what's left here is exactly the same real data,
// laid out for paper instead of a screen.
function PrintableAuditReport({ auditId, audits }: { auditId: string; audits: SeoAudit[] }) {
  const { t } = useT()
  return (
    <div className="hidden print:block">
      <section>
        <ReportView auditId={auditId} />
      </section>

      <section className="print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">{t('seo.print.plan')}</h2>
        <ActionPlanList auditId={auditId} />
      </section>

      <section className="mt-8 print:mt-0 print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">{t('seo.print.findings')}</h2>
        <FindingsList auditId={auditId} severityFilter={null} />
      </section>

      <section className="mt-8 print:mt-0 print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">{t('seo.print.keywords')}</h2>
        <KeywordOpportunitiesList auditId={auditId} />
      </section>

      <section className="mt-8 print:mt-0 print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">{t('seo.print.history')}</h2>
        <AuditHistoryList audits={audits} />
      </section>
    </div>
  )
}

// Stage 2 of the SEO Audit & Optimization upgrade (see apps/agents/
// seo-audit/CLAUDE.md) -- crawl a registered website and store
// per-page facts. Findings/health scores/recommendations are later stages
// of that same plan; this is just "run a crawl and see it finish".
function WebsiteCard({ website, onDelete, deleting }: { website: SeoWebsite; onDelete: () => void; deleting: boolean }) {
  const qc = useQueryClient()
  const { t, tCode, formatDate, formatNumber } = useT()
  const [showFindings, setShowFindings] = useState(false)
  const [severityFilter, setSeverityFilter] = useState<Severity | null>(null)
  const [detailTab, setDetailTab] = useState<'findings' | 'plan' | 'keywords' | 'history' | 'report'>('plan')
  const { data: audits = [] } = useQuery<SeoAudit[]>({
    queryKey: ['seo', 'audits', website.id],
    queryFn: () => api.get(`/agents/seo/websites/${website.id}/audits`).then((r) => r.data),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0]
      return latest && (latest.status === 'pending' || latest.status === 'running') ? 2000 : false
    },
  })
  const latestAudit = audits[0]

  const runAuditMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/websites/${website.id}/audits`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo', 'audits', website.id] })
      setShowFindings(false)
    },
  })

  // Stage 15 (recurring audits) -- invalidating the parent's ['seo',
  // 'websites'] query from here is fine even though WebsiteCard doesn't
  // own that query itself; React Query invalidation is keyed globally, not
  // scoped to whichever component created the query, so this flows the
  // updated audit_schedule/next_scheduled_audit_at back down as new props.
  const scheduleMut = useMutation({
    mutationFn: (interval: 'weekly' | 'monthly' | null) =>
      api.patch(`/agents/seo/websites/${website.id}/schedule`, { interval }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo', 'websites'] }),
  })

  return (
    <Card className={showFindings ? 'print:rounded-none print:border-0 print:shadow-none' : 'print:hidden'}>
      <div className="flex items-start justify-between gap-4 print:hidden">
        <div>
          <p className="flex items-center gap-2 font-semibold text-slate-900">
            <Globe size={16} className="text-slate-400" />
            {website.name || website.url}
          </p>
          <p className="mt-1 text-sm text-slate-500">{website.url}</p>
          <p className="mt-2 text-sm text-slate-400">
            {[website.target_country, website.target_language].filter(Boolean).join(' · ') || t('seo.website.noTarget')}
            {' · '}
            {t('seo.website.tier', { tier: tCode('seo.website.tiers', website.crawl_tier) })}
          </p>
          <div className="mt-2 flex items-center gap-2 text-sm">
            <label htmlFor={`seo-schedule-${website.id}`} className="text-slate-400">{t('seo.website.recurring')}</label>
            <select
              id={`seo-schedule-${website.id}`}
              value={website.audit_schedule ?? ''}
              disabled={scheduleMut.isPending}
              onChange={(e) => scheduleMut.mutate((e.target.value || null) as 'weekly' | 'monthly' | null)}
              className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">{t('seo.website.schedule.off')}</option>
              <option value="weekly">{t('seo.website.schedule.weekly')}</option>
              <option value="monthly">{t('seo.website.schedule.monthly')}</option>
            </select>
            {website.audit_schedule && website.next_scheduled_audit_at && (
              <span className="text-slate-400">
                {t('seo.website.next', { date: formatDate(website.next_scheduled_audit_at) })}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" loading={runAuditMut.isPending} onClick={() => runAuditMut.mutate()}>
            <PlayCircle size={16} className="mr-1" />
            {t('seo.website.runAudit')}
          </Button>
          <Button size="sm" variant="ghost" loading={deleting} onClick={onDelete} aria-label={t('seo.website.delete')} title={t('seo.website.delete')}>
            <Trash2 size={16} />
          </Button>
        </div>
      </div>

      {latestAudit && (
        <div className="mt-4 flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm print:hidden">
          <span className={clsx('rounded-full px-2 py-0.5 font-medium', AUDIT_STATUS_COLORS[latestAudit.status])}>
            {tCode('seo.auditStatus', latestAudit.status)}
          </span>
          <span className="text-slate-500">
            {t('seo.website.crawled', { count: formatNumber(latestAudit.pages_crawled) })}
            {latestAudit.pages_discovered > 0 && t('seo.website.discovered', { count: formatNumber(latestAudit.pages_discovered) })}
            {latestAudit.pages_blocked > 0 && t('seo.website.blocked', { count: formatNumber(latestAudit.pages_blocked) })}
            {latestAudit.pages_in_sitemap != null && t('seo.website.inSitemap', { count: formatNumber(latestAudit.pages_in_sitemap) })}
          </span>
          {latestAudit.status === 'completed' && (
            <Button className="ml-auto" size="sm" variant="ghost" onClick={() => setShowFindings((v) => !v)}>
              {showFindings ? t('seo.website.hideHealth') : t('seo.website.viewHealth')}
            </Button>
          )}
        </div>
      )}

      {showFindings && latestAudit && (
        <>
          <div className="print:hidden">
            <SeoHealthPanel audit={latestAudit} severityFilter={severityFilter} onSeverityFilter={setSeverityFilter} />
          </div>
          <div className="mt-3 flex items-center justify-between gap-2 border-b border-slate-200 print:hidden">
            <div className="flex gap-2">
              {(['plan', 'findings', 'keywords', 'history', 'report'] as const).map((key) => (
                <button
                  key={key}
                  onClick={() => setDetailTab(key)}
                  aria-pressed={detailTab === key}
                  className={clsx(
                    'px-3 py-1.5 text-sm font-medium border-b-2 -mb-px',
                    detailTab === key ? 'border-brand-600 text-brand-600' : 'border-transparent text-slate-500',
                  )}
                >
                  {t(`seo.website.tabs.${key}`)}
                </button>
              ))}
            </div>
            {/* One button prints the FULL report (all five sections below,
                via PrintableAuditReport) regardless of which tab is active
                on screen -- see that component's own docstring for why a
                per-tab print button couldn't do this. */}
            <Button size="sm" variant="secondary" className="mb-2" onClick={() => window.print()}>
              {t('seo.website.printFull')}
            </Button>
          </div>
          <div className="mt-3 print:hidden">
            {detailTab === 'plan' ? (
              <ActionPlanList auditId={latestAudit.id} />
            ) : detailTab === 'findings' ? (
              <FindingsList auditId={latestAudit.id} severityFilter={severityFilter} />
            ) : detailTab === 'keywords' ? (
              <KeywordOpportunitiesList auditId={latestAudit.id} />
            ) : detailTab === 'history' ? (
              <AuditHistoryList audits={audits} />
            ) : (
              <ReportView auditId={latestAudit.id} />
            )}
          </div>
          <PrintableAuditReport auditId={latestAudit.id} audits={audits} />
        </>
      )}
    </Card>
  )
}

// Stage 12 (Google Analytics + Search Console, see apps/agents/seo-audit/
// CLAUDE.md's "Professional tier roadmap") -- one connection per business,
// not per website, so this lives above the website list rather than on
// each WebsiteCard. Same OAuth-redirect-banner pattern as Booking
// Assistant's Google Calendar connect card (dashboard/pages/settings/
// BookingSection.tsx) -- window.location.href to the backend's own
// /authorize route (a real browser redirect to Google, not an API call),
// and ?google=connected|error stripped from the URL right after reading it
// so a page refresh doesn't keep re-showing a banner from a connection
// attempt that already happened.
function GoogleConnectionCard() {
  const qc = useQueryClient()
  const { t } = useT()
  const [searchParams, setSearchParams] = useSearchParams()
  const [banner, setBanner] = useState<'connected' | 'error' | null>(null)
  const [propertyId, setPropertyId] = useState('')
  const [siteUrl, setSiteUrl] = useState('')

  const { data: status } = useQuery<SeoGoogleStatus>({
    queryKey: ['seo-google-status'],
    queryFn: () => api.get('/businesses/me/google/status').then((r) => r.data),
  })

  useEffect(() => {
    const value = searchParams.get('google')
    if (value === 'connected' || value === 'error') {
      setBanner(value)
      qc.invalidateQueries({ queryKey: ['seo-google-status'] })
      const next = new URLSearchParams(searchParams)
      next.delete('google')
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Pre-fill the property/site inputs from whatever's already saved, once
  // the status query resolves -- lets a business edit an existing value
  // instead of always starting from a blank field.
  useEffect(() => {
    setPropertyId(status?.analytics_property_id ?? '')
    setSiteUrl(status?.search_console_site_url ?? '')
  }, [status?.analytics_property_id, status?.search_console_site_url])

  const configMut = useMutation({
    mutationFn: () =>
      api.patch('/businesses/me/google/config', {
        analytics_property_id: propertyId.trim() || null,
        search_console_site_url: siteUrl.trim() || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-google-status'] }),
  })

  const disconnectMut = useMutation({
    mutationFn: () => api.delete('/businesses/me/google'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-google-status'] }),
  })

  return (
    <Card title={t('seo.google.title')} className="print:hidden">
      <div className="space-y-3">
        {banner === 'connected' && <p role="status" className="text-base text-green-600">{t('seo.google.connectedBanner')}</p>}
        {banner === 'error' && <p role="alert" className="text-base text-red-600">{t('seo.google.connectFailed')}</p>}

        {status?.connected ? (
          <>
            <p className="text-base text-slate-700">
              {status.google_account_email
                ? t('seo.google.connectedAs', { email: status.google_account_email })
                : t('seo.google.connectedPlain')}
            </p>
            <p className="text-sm text-slate-500">{t('seo.google.connectedHelp')}</p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label htmlFor="seo-ga4-property" className="text-sm text-slate-500">{t('seo.google.propertyId')}</label>
                <input
                  id="seo-ga4-property"
                  placeholder="properties/123456789"
                  value={propertyId}
                  onChange={(e) => setPropertyId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
                />
              </div>
              <div>
                <label htmlFor="seo-gsc-site" className="text-sm text-slate-500">{t('seo.google.siteUrl')}</label>
                <input
                  id="seo-gsc-site"
                  placeholder={t('seo.google.siteUrlPlaceholder')}
                  value={siteUrl}
                  onChange={(e) => setSiteUrl(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" loading={configMut.isPending} onClick={() => configMut.mutate()}>
                {t('seo.google.save')}
              </Button>
              <Button size="sm" variant="secondary" loading={disconnectMut.isPending} onClick={() => disconnectMut.mutate()}>
                {t('seo.google.disconnect')}
              </Button>
              {configMut.isSuccess && <span role="status" className="text-sm text-green-600">{t('seo.google.saved')}</span>}
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-500">{t('seo.google.connectHelp')}</p>
            <Button
              onClick={() => {
                window.location.href = `${api.defaults.baseURL}/businesses/me/google/authorize`
              }}
            >
              {t('seo.google.connect')}
            </Button>
          </>
        )}
      </div>
    </Card>
  )
}

// Stage 1 of the SEO Audit & Optimization upgrade (see apps/agents/
// seo-audit/CLAUDE.md) -- register websites to audit. Audit runs,
// findings, and recommendations land in later stages of that same plan.
function WebsitesTab() {
  const qc = useQueryClient()
  const { t } = useT()
  const { data: websites = [] } = useQuery<SeoWebsite[]>({
    queryKey: ['seo', 'websites'],
    queryFn: () => api.get('/agents/seo/websites').then((r) => r.data),
  })

  const [url, setUrl] = useState('')
  const [name, setName] = useState('')
  const [targetCountry, setTargetCountry] = useState('')
  const [targetLanguage, setTargetLanguage] = useState('')
  const [crawlTier, setCrawlTier] = useState<'starter' | 'standard' | 'advanced'>('starter')

  const createMut = useMutation({
    mutationFn: () =>
      api.post('/agents/seo/websites', {
        url,
        name: name || null,
        target_country: targetCountry || null,
        target_language: targetLanguage || null,
        crawl_tier: crawlTier,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo', 'websites'] })
      setUrl('')
      setName('')
      setTargetCountry('')
      setTargetLanguage('')
      setCrawlTier('starter')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/agents/seo/websites/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo', 'websites'] }),
  })

  return (
    <div className="space-y-6">
      <GoogleConnectionCard />

      <Card title={t('seo.add.title')} className="print:hidden">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            createMut.mutate()
          }}
        >
          <input
            type="url"
            required
            placeholder={t('seo.add.urlPlaceholder')}
            aria-label={t('seo.add.url')}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
          />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <input
              placeholder={t('seo.add.name')}
              aria-label={t('seo.add.name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-base"
            />
            <input
              placeholder={t('seo.add.country')}
              aria-label={t('seo.add.country')}
              value={targetCountry}
              onChange={(e) => setTargetCountry(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-base"
            />
            <input
              placeholder={t('seo.add.language')}
              aria-label={t('seo.add.language')}
              value={targetLanguage}
              onChange={(e) => setTargetLanguage(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-base"
            />
          </div>
          <div className="flex items-center gap-3">
            <label htmlFor="seo-crawl-depth" className="text-sm text-slate-500">{t('seo.add.depth')}</label>
            <select
              id="seo-crawl-depth"
              value={crawlTier}
              onChange={(e) => setCrawlTier(e.target.value as typeof crawlTier)}
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-base"
            >
              <option value="starter">{t('seo.add.depths.starter')}</option>
              <option value="standard">{t('seo.add.depths.standard')}</option>
              <option value="advanced">{t('seo.add.depths.advanced')}</option>
            </select>
          </div>
          <Button type="submit" size="sm" loading={createMut.isPending} disabled={!url}>
            {t('seo.add.submit')}
          </Button>
          {createMut.isError && (
            <p role="alert" className="text-sm text-red-600">{apiErrorMessage(createMut.error, 'seo.add.failed')}</p>
          )}
        </form>
      </Card>

      <div className="space-y-3">
        {websites.map((w) => (
          <WebsiteCard
            key={w.id}
            website={w}
            onDelete={() => deleteMut.mutate(w.id)}
            deleting={deleteMut.isPending && deleteMut.variables === w.id}
          />
        ))}
        {websites.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">
            {t('seo.add.empty')}
          </div>
        )}
      </div>
    </div>
  )
}

interface Product {
  id: string
  name: string
  description: string | null
  seo_title: string | null
  meta_description: string | null
}

interface SeoDraft {
  id: string
  product_id: string | null
  finding_id: string | null
  url: string | null
  draft_type: 'full_copy' | 'title' | 'meta_description' | 'content'
  draft_description: string | null
  draft_seo_title: string | null
  draft_meta_description: string | null
  status: 'draft' | 'approved' | 'rejected'
}

// Only ever "generate for products I picked, review, approve/reject" -- see
// apps/agents/seo-audit/CLAUDE.md: silently overwriting live product
// copy without a review step is the one failure mode this agent must never
// have, so nothing here ever calls PATCH /products directly.
function DraftReview({ product, draft }: { product: Product; draft: SeoDraft }) {
  const qc = useQueryClient()
  const { t } = useT()

  const approveMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/drafts/${draft.id}/approve`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo', 'drafts'] })
      qc.invalidateQueries({ queryKey: ['products'] })
    },
  })
  const rejectMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/drafts/${draft.id}/reject`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo', 'drafts'] }),
  })

  return (
    <Card>
      <p className="font-semibold text-slate-900 text-lg">{product.name}</p>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wide">{t('seo.content.liveNow')}</p>
          <p className="mt-1 text-base text-slate-600">{product.description || t('seo.content.noDescription')}</p>
          <p className="mt-2 text-sm text-slate-400">{t('seo.content.seoTitle', { value: product.seo_title || '-' })}</p>
          <p className="text-sm text-slate-400">{t('seo.content.meta', { value: product.meta_description || '-' })}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-brand-600 uppercase tracking-wide">{t('seo.content.draft')}</p>
          <p className="mt-1 text-base text-slate-900">{draft.draft_description || '-'}</p>
          <p className="mt-2 text-sm text-slate-600">{t('seo.content.seoTitle', { value: draft.draft_seo_title || '-' })}</p>
          <p className="text-sm text-slate-600">{t('seo.content.meta', { value: draft.draft_meta_description || '-' })}</p>
        </div>
      </div>

      <div className="mt-4 flex gap-2">
        <Button size="sm" loading={approveMut.isPending} onClick={() => approveMut.mutate()}>
          <Check size={16} className="mr-1" />
          {t('seo.content.approve')}
        </Button>
        <Button size="sm" variant="secondary" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
          <X size={16} className="mr-1" />
          {t('seo.content.reject')}
        </Button>
      </div>
    </Card>
  )
}

function ContentTab() {
  const qc = useQueryClient()
  const { t } = useT()
  const { data: products = [] } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products').then((r) => r.data),
  })
  const { data: drafts = [] } = useQuery<SeoDraft[]>({
    queryKey: ['seo', 'drafts', 'draft'],
    queryFn: () => api.get('/agents/seo/drafts', { params: { status: 'draft' } }).then((r) => r.data),
  })

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const generateMut = useMutation({
    mutationFn: () => api.post('/agents/seo/drafts/generate', { product_ids: [...selected] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo', 'drafts'] })
      setSelected(new Set())
    },
  })

  const productById = new Map(products.map((p) => [p.id, p]))

  return (
    <div className="space-y-6">
      <Card title={t('seo.content.pickTitle')}>
        <div className="space-y-2">
          {products.map((p) => (
            <label key={p.id} className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => toggle(p.id)}
                className="h-4 w-4 rounded border-slate-300"
              />
              <span className="text-base text-slate-700">{p.name}</span>
            </label>
          ))}
          {products.length === 0 && <p className="text-base text-slate-400">{t('seo.content.addProductsFirst')}</p>}
        </div>
        <Button
          className="mt-4"
          size="sm"
          disabled={selected.size === 0}
          loading={generateMut.isPending}
          onClick={() => generateMut.mutate()}
        >
          <Sparkles size={16} className="mr-1" />
          {t('seo.content.generate', { count: selected.size })}
        </Button>
        {generateMut.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">{apiErrorMessage(generateMut.error, 'seo.content.failed')}</p>
        )}
      </Card>

      <div className="space-y-4">
        {drafts.map((draft) => {
          // Finding-driven drafts (Stage 7) have no product_id -- they're
          // reviewed inline on the finding itself (WebsiteCard's findings
          // list), not here, so this tab only ever shows product drafts.
          if (!draft.product_id) return null
          const product = productById.get(draft.product_id)
          if (!product) return null
          return <DraftReview key={draft.id} product={product} draft={draft} />
        })}
        {drafts.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">
            {t('seo.content.empty')}
          </div>
        )}
      </div>
    </div>
  )
}

// Two-tier pricing card, same visual language as PlanPage.tsx's chat-widget
// plan cards (brand-gradient "Most Popular" card for the paid tier) so the
// two pricing surfaces in this app don't look like two different products.
function SeoTierCard({ tier, isCurrent, format }: { tier: AgentTier; isCurrent: boolean; format: (nokAmount: number) => string }) {
  const navigate = useNavigate()
  const { t } = useT()
  const isFree = tier.key === 'free'
  // NOK/month excl. MVA (agent_catalog.py's price_nok), shown in the chosen currency (useCurrency).
  const priceLabel = isFree ? t('seo.plans.free') : format(tier.price_nok)

  return (
    <div
      className={clsx(
        'flex flex-col rounded-2xl border p-6 print:break-inside-avoid print:border-slate-300',
        !isFree ? 'brand-gradient text-white shadow-sm shadow-brand-200 print:bg-none print:text-slate-900' : 'bg-white border-slate-300',
      )}
    >
      {!isFree && (
        <span className="mb-2 inline-flex w-fit items-center gap-1 rounded-full bg-white/20 px-2.5 py-1 text-sm font-semibold print:border print:border-slate-300 print:bg-transparent print:text-slate-700">
          <Star size={12} /> {t('seo.plans.mostPopular')}
        </span>
      )}
      <h3 className={clsx('text-xl font-bold', !isFree ? 'text-white print:text-slate-900' : 'text-slate-900')}>{tier.name}</h3>
      <p className={clsx('text-sm mt-1', !isFree ? 'text-brand-50 print:text-slate-500' : 'text-slate-500')}>{tier.tagline}</p>
      <p className="mt-4">
        <span className={clsx('text-3xl font-bold', !isFree ? 'text-white print:text-slate-900' : 'text-slate-900')}>{priceLabel}</span>
        {!isFree && <span className={clsx('text-sm', !isFree ? 'text-brand-50 print:text-slate-500' : 'text-slate-500')}>{t('seo.plans.perMonth')}</span>}
      </p>

      <Button
        className="mt-4 w-full justify-center print:hidden"
        variant={!isFree ? 'secondary' : isCurrent ? 'secondary' : 'primary'}
        disabled={isCurrent}
        onClick={() => navigate('/dashboard/plan')}
      >
        {isCurrent ? t('seo.plans.currentPlan') : isFree ? t('seo.plans.activate') : t('seo.plans.upgrade')}
      </Button>

      <ul className="mt-5 space-y-2 flex-1">
        {tier.features.map((line) => (
          <li key={line} className={clsx('flex items-start gap-2 text-sm', !isFree ? 'text-white print:text-slate-600' : 'text-slate-600')}>
            <Check size={15} className={clsx('mt-0.5 flex-shrink-0', !isFree ? 'text-white print:text-emerald-600' : 'text-emerald-600')} />
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}

// No payment processor exists yet (same PAYMENT_COMING_SOON situation as
// PlanPage.tsx), and activating a purchased agent is still a platform-admin
// action (see businesses.py's "Force agents" section) -- so both tiers'
// buttons hand off to Plan & Billing rather than pretending to check out.
// "Current plan" only ever shows for the free tier: BusinessAgentAccess has
// no tier column (tiers are catalog/pricing copy, not a second entitlement
// gate -- see agent_catalog.py's AgentTier docstring), and every capability
// the free tier lists is already what an active grant unlocks today, so
// treating "has access at all" as "on the free tier" is accurate, not a
// guess.
function PlansTab() {
  const { data: catalog } = useAgentCatalog()
  const { data: access } = useAgentAccess()
  const { currency, setCurrency, format, converted } = useCurrency()
  const { t } = useT()
  const seo = catalog?.find((a) => a.key === 'seo_audit_optimization')

  if (!seo?.tiers) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 print:hidden">
        <p className="text-base text-slate-500 max-w-2xl">
          {t('seo.plans.intro')}
          {converted && t('seo.plans.approx')}
        </p>
        <div className="flex items-center gap-2">
          <CurrencySwitcher currency={currency} onChange={setCurrency} />
          <Button size="sm" variant="secondary" onClick={() => window.print()}>
            {t('seo.plans.print')}
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {seo.tiers.map((tier) => (
          <SeoTierCard
            key={tier.key}
            tier={tier}
            isCurrent={tier.key === 'free' && !!access?.seo_audit_optimization}
            format={format}
          />
        ))}
      </div>
    </div>
  )
}

const TABS = ['websites', 'content', 'plans'] as const

export function SeoPage() {
  const { data: access, isLoading } = useAgentAccess()
  const { t } = useT()
  const [tab, setTab] = useState<(typeof TABS)[number]>('websites')
  if (isLoading) return null

  if (!access?.seo_audit_optimization) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">{t('seo.title')}</h1>
        <AgentGate agentKey="seo_audit_optimization">
          <span />
        </AgentGate>
        <PlansTab />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="print:hidden">
        <h1 className="text-4xl font-bold text-slate-900">{t('seo.title')}</h1>
        <p className="text-base text-slate-500 mt-1">{t('seo.subtitle')}</p>
      </div>

      <div className="flex gap-2 border-b border-slate-200 print:hidden">
        {TABS.map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            aria-pressed={tab === key}
            className={clsx(
              'px-4 py-2 text-base font-medium border-b-2 -mb-px transition-colors',
              tab === key
                ? 'border-brand-600 text-brand-600'
                : 'border-transparent text-slate-500 hover:text-slate-700',
            )}
          >
            {t(`seo.tabs.${key}`)}
          </button>
        ))}
      </div>

      {tab === 'websites' ? <WebsitesTab /> : tab === 'content' ? <ContentTab /> : <PlansTab />}
    </div>
  )
}
