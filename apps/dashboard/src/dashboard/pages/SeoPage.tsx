import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Check, X, Trash2, Globe, PlayCircle, Star } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { AgentGate } from '../../shared/components/AgentGate'
import { useAgentAccess, useAgentCatalog, AgentTier } from '../../shared/hooks/usePlan'
import { formatCurrency } from '../../shared/currency'

interface SeoWebsite {
  id: string
  url: string
  name: string | null
  target_country: string | null
  target_language: string | null
  primary_category: string | null
  target_keywords: string[]
  crawl_tier: 'starter' | 'standard' | 'advanced'
  created_at: string
}

type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'

interface SeoAudit {
  id: string
  website_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  pages_discovered: number
  pages_crawled: number
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
}

const PRIORITY_LABELS: Record<number, string> = {
  1: 'Priority 1 — Critical',
  2: 'Priority 2 — High',
  3: 'Priority 3 — Medium & Below',
}

const HEALTH_CATEGORIES: { key: keyof SeoAudit; label: string }[] = [
  { key: 'health_technical', label: 'Technical' },
  { key: 'health_on_page', label: 'On-Page' },
  { key: 'health_performance', label: 'Performance' },
  { key: 'health_content', label: 'Content' },
  { key: 'health_internal_linking', label: 'Internal Linking' },
]

const SEVERITY_LABELS: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  informational: 'Info',
}

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
  const { data: measurements = [] } = useQuery<SeoPerformanceMeasurement[]>({
    queryKey: ['seo', 'performance', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/performance`).then((r) => r.data),
  })

  if (measurements.length === 0) return null

  return (
    <div className="flex flex-wrap gap-4 rounded-lg bg-white p-3 text-sm border border-slate-200">
      {measurements.map((m) => (
        <div key={m.strategy}>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{m.strategy}</p>
          <p className="text-slate-600">
            {m.performance_score !== null ? `Score: ${m.performance_score}/100` : 'Score: —'}
            {m.lcp_ms !== null && ` · LCP: ${(m.lcp_ms / 1000).toFixed(1)}s`}
            {m.cls_score !== null && ` · CLS: ${m.cls_score}`}
            {m.inp_ms !== null ? ` · INP: ${m.inp_ms}ms` : m.tbt_ms !== null ? ` · TBT: ${m.tbt_ms}ms` : ''}
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
  return (
    <div className="mt-4 space-y-3 rounded-lg bg-slate-50 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-500">
            SEO Health <span className="text-xs text-slate-400">(internal diagnostic score, not a Google ranking signal)</span>
          </p>
          <p className="text-3xl font-bold text-slate-900">
            {audit.overall_health !== null ? `${audit.overall_health}/100` : '—'}
          </p>
        </div>
        <div className="flex gap-4">
          {HEALTH_CATEGORIES.map(({ key, label }) => (
            <div key={key} className="text-center">
              <p className="text-lg font-semibold text-slate-700">
                {audit[key] !== null ? (audit[key] as number) : '—'}
              </p>
              <p className="text-xs text-slate-400">{label}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 print:hidden">
        {(Object.keys(SEVERITY_LABELS) as Severity[]).map((severity) => (
          <button
            key={severity}
            onClick={() => onSeverityFilter(severityFilter === severity ? null : severity)}
            className={clsx(
              'rounded-full px-3 py-1 text-sm font-medium transition-colors',
              severityFilter === severity ? SEVERITY_COLORS[severity] : 'bg-white text-slate-500 border border-slate-200',
            )}
          >
            {SEVERITY_LABELS[severity]}: {audit.finding_counts[severity]}
          </button>
        ))}
      </div>
      {/* Print-only static equivalent of the interactive filter buttons above
          -- the numbers are useful in a printed report, the click-to-filter
          behavior isn't. */}
      <div className="hidden flex-wrap gap-3 text-sm print:flex">
        {(Object.keys(SEVERITY_LABELS) as Severity[])
          .filter((s) => audit.finding_counts[s] > 0)
          .map((severity) => (
            <span key={severity} className="rounded-full border border-slate-300 px-3 py-1">
              {SEVERITY_LABELS[severity]}: {audit.finding_counts[severity]}
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
  const { data: items = [], isLoading } = useQuery<ActionPlanItem[]>({
    queryKey: ['seo', 'action-plan', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/action-plan`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-400">Loading action plan…</p>
  if (items.length === 0) return <p className="text-sm text-slate-400">No action items -- nothing found to fix.</p>

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
            <h4 className="mb-2 text-sm font-semibold text-slate-700">{PRIORITY_LABELS[priority]}</h4>
            <div className="space-y-2">
              {group.map((item) => (
                <div key={item.rule_code} className={clsx('rounded-lg border px-3 py-2 print:break-inside-avoid', item.status === 'ignored' && 'opacity-50')}>
                  <p className="font-medium text-slate-800">{item.issue}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    {item.affected_urls.length} page(s) affected · Difficulty: {item.implementation_difficulty} · Benefit: {item.expected_benefit}
                  </p>
                  {item.recommended_action && <p className="mt-1 text-sm text-slate-700">Fix: {item.recommended_action}</p>}
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
  const { data: report, isLoading, isError } = useQuery<SeoAuditReport>({
    queryKey: ['seo', 'report', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/report`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-400">Building report…</p>
  if (isError || !report) {
    return <p className="text-sm text-red-500">Report isn't available yet -- the audit may still be running.</p>
  }

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 print:border-0 print:p-0">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">SEO Report — {report.website_name || report.website_url}</h3>
        <p className="text-sm text-slate-500">
          {report.website_url}
          {report.audit_completed_at && ` · Generated ${new Date(report.audit_completed_at).toLocaleDateString()}`}
        </p>
      </div>

      <div className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 print:border print:border-slate-300">
        <span className="text-2xl font-bold text-slate-900">{report.overall_health ?? '—'}</span>
        <span className="text-sm text-slate-500">Overall SEO health (internal diagnostic score, not a Google ranking)</span>
      </div>

      {report.executive_summary && (
        <div>
          <h4 className="mb-1 text-sm font-semibold text-slate-700">Summary</h4>
          <p className="text-sm text-slate-700">{report.executive_summary}</p>
        </div>
      )}

      <div>
        <h4 className="mb-1 text-sm font-semibold text-slate-700">Issues found</h4>
        <div className="flex flex-wrap gap-3 text-sm">
          {(Object.keys(report.finding_counts) as Severity[])
            .filter((s) => report.finding_counts[s] > 0)
            .map((severity) => (
              <span key={severity} className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
                {report.finding_counts[severity]} {severity}
              </span>
            ))}
          {Object.values(report.finding_counts).every((c) => c === 0) && (
            <span className="text-slate-400">No issues found.</span>
          )}
        </div>
      </div>

      {report.top_action_items.length > 0 && (
        <div>
          <h4 className="mb-1 text-sm font-semibold text-slate-700">Top priorities</h4>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
            {report.top_action_items.map((item) => (
              <li key={item.rule_code}>
                {item.issue} ({item.affected_urls.length} page(s), {item.implementation_difficulty} fix)
              </li>
            ))}
          </ol>
        </div>
      )}

      <p className="text-sm text-slate-500">{report.keyword_opportunity_count} keyword opportunit{report.keyword_opportunity_count === 1 ? 'y' : 'ies'} identified.</p>
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
  const { data, isLoading, isError } = useQuery<SeoAuditComparison>({
    queryKey: ['seo', 'compare', currentAuditId, previousAuditId],
    queryFn: () =>
      api
        .get(`/agents/seo/audits/${currentAuditId}/compare`, { params: { against: previousAuditId } })
        .then((r) => r.data),
  })

  if (isLoading) return <p className="mt-2 text-sm text-slate-400">Comparing…</p>
  if (isError || !data) return <p className="mt-2 text-sm text-red-500">Could not compare these audits.</p>

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
      <p className="font-medium text-slate-700">
        Overall health: {data.overall_health_previous ?? '—'} → {data.overall_health_current ?? '—'}
        {data.overall_health_delta !== null && (
          <span className={clsx('ml-2 font-semibold', data.overall_health_delta >= 0 ? 'text-green-600' : 'text-red-600')}>
            ({data.overall_health_delta >= 0 ? '+' : ''}
            {data.overall_health_delta})
          </span>
        )}
      </p>
      <div className="flex gap-4">
        <span className="text-green-700">{data.resolved_findings.length} resolved</span>
        <span className="text-amber-700">{data.new_findings.length} new</span>
        <span className="text-slate-500">{data.persisting_findings.length} still open</span>
      </div>
      {data.resolved_findings.length > 0 && (
        <div>
          <p className="font-medium text-slate-600">Resolved</p>
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
          <p className="font-medium text-slate-600">New</p>
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
  const completed = audits.filter((a) => a.status === 'completed')

  if (completed.length === 0) return <p className="text-sm text-slate-400">No completed audits yet.</p>

  return (
    <div className="space-y-2">
      {completed.map((audit, i) => {
        const previous = completed[i + 1]
        return (
          <div key={audit.id} className="rounded-lg border border-slate-200 px-3 py-2 print:break-inside-avoid">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-medium text-slate-800">{new Date(audit.created_at).toLocaleString()}</p>
                <p className="text-sm text-slate-500">Overall health: {audit.overall_health ?? 'Not yet scored'}</p>
              </div>
              {previous && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="print:hidden"
                  onClick={() => setComparingId((v) => (v === audit.id ? null : audit.id))}
                >
                  {comparingId === audit.id ? 'Hide comparison' : 'Compare to previous'}
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
  const { data: keywords = [], isLoading } = useQuery<SeoKeywordOpportunity[]>({
    queryKey: ['seo', 'keyword-opportunities', auditId],
    queryFn: () => api.get(`/agents/seo/audits/${auditId}/keyword-opportunities`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-400">Loading keyword ideas…</p>
  if (keywords.length === 0) return <p className="text-sm text-slate-400">No keyword ideas generated for this audit.</p>

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-400">
        Search volume/CPC/competition: <span className="font-medium">Not available</span> -- no real keyword-data source is connected.
      </p>
      {keywords.map((k) => (
        <div key={k.id} className="rounded-lg border border-slate-200 px-3 py-2 print:break-inside-avoid">
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-800">{k.keyword}</span>
            {k.intent && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{k.intent}</span>}
          </div>
          {k.content_gap && <p className="mt-1 text-sm text-amber-700">Content gap: {k.content_gap}</p>}
          {k.current_page && <p className="mt-1 text-sm text-slate-500">Already covered by: {k.current_page}</p>}
          {k.suggested_page && !k.current_page && <p className="mt-1 text-sm text-slate-500">Suggested page: {k.suggested_page}</p>}
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
          {latest?.status === 'rejected' ? 'Regenerate fix' : 'Generate fix'}
        </Button>
        {generateMut.isError && <p className="mt-1 text-sm text-red-600">Couldn't generate a fix. Try again.</p>}
      </div>
    )
  }

  return (
    <div className="mt-2 rounded-lg bg-brand-50 border border-brand-100 px-3 py-2 print:border-slate-300 print:bg-transparent">
      <p className="text-xs font-medium uppercase tracking-wide text-brand-600">Suggested fix</p>
      <p className="mt-1 text-sm text-slate-800">{draftText}</p>
      {latest.status === 'draft' ? (
        <div className="mt-2 flex gap-2 print:hidden">
          <Button size="sm" loading={approveMut.isPending} onClick={() => approveMut.mutate()}>
            <Check size={14} className="mr-1" />
            Approve
          </Button>
          <Button size="sm" variant="secondary" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
            <X size={14} className="mr-1" />
            Reject
          </Button>
        </div>
      ) : (
        <p className="mt-1 text-xs font-medium text-emerald-600">Approved -- ready to use.</p>
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

  if (isLoading) return <p className="text-sm text-slate-400">Loading findings…</p>
  if (findings.length === 0) {
    return <p className="text-sm text-slate-400">{severityFilter ? `No ${severityFilter} findings.` : 'No issues found.'}</p>
  }

  return (
    <div className="space-y-2">
      {findings.map((f) => (
        <div key={f.id} className={clsx('rounded-lg border px-3 py-2 print:break-inside-avoid', f.status === 'ignored' ? 'opacity-50 border-slate-100' : 'border-slate-200')}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className={clsx('mr-2 rounded-full px-2 py-0.5 text-xs font-medium uppercase', SEVERITY_COLORS[f.severity])}>
                {f.severity}
              </span>
              <span className="font-medium text-slate-800">{f.issue}</span>
              {f.affected_url && <p className="mt-1 text-sm text-slate-500 break-all">{f.affected_url}</p>}
              {f.explanation && <p className="mt-1 text-sm text-slate-500">{f.explanation}</p>}
              {f.recommended_fix && <p className="mt-1 text-sm text-slate-700">Fix: {f.recommended_fix}</p>}
              {f.status !== 'ignored' && COPYWRITER_RULE_CODES.has(f.rule_code) && <FindingDraftAction finding={f} />}
            </div>
            {f.status !== 'ignored' && (
              <Button size="sm" variant="ghost" className="print:hidden" loading={ignoreMut.isPending} onClick={() => ignoreMut.mutate(f.id)}>
                Ignore
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
  return (
    <div className="hidden print:block">
      <section>
        <ReportView auditId={auditId} />
      </section>

      <section className="print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">Action Plan</h2>
        <ActionPlanList auditId={auditId} />
      </section>

      <section className="mt-8 print:mt-0 print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">All Findings</h2>
        <FindingsList auditId={auditId} severityFilter={null} />
      </section>

      <section className="mt-8 print:mt-0 print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">Keyword Ideas</h2>
        <KeywordOpportunitiesList auditId={auditId} />
      </section>

      <section className="mt-8 print:mt-0 print:break-before-page">
        <h2 className="mb-3 border-b border-slate-300 pb-1.5 text-xl font-bold text-slate-900">Audit History</h2>
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
            {[website.target_country, website.target_language].filter(Boolean).join(' · ') || 'No target set'}
            {' · '}
            {website.crawl_tier} tier
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" loading={runAuditMut.isPending} onClick={() => runAuditMut.mutate()}>
            <PlayCircle size={16} className="mr-1" />
            Run audit
          </Button>
          <Button size="sm" variant="ghost" loading={deleting} onClick={onDelete}>
            <Trash2 size={16} />
          </Button>
        </div>
      </div>

      {latestAudit && (
        <div className="mt-4 flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm print:hidden">
          <span className={clsx('rounded-full px-2 py-0.5 font-medium', AUDIT_STATUS_COLORS[latestAudit.status])}>
            {latestAudit.status}
          </span>
          <span className="text-slate-500">
            {latestAudit.pages_crawled} crawled
            {latestAudit.pages_discovered > 0 && ` of ${latestAudit.pages_discovered} discovered`}
            {latestAudit.pages_blocked > 0 && ` · ${latestAudit.pages_blocked} blocked`}
          </span>
          {latestAudit.status === 'completed' && (
            <Button className="ml-auto" size="sm" variant="ghost" onClick={() => setShowFindings((v) => !v)}>
              {showFindings ? 'Hide SEO Health' : 'View SEO Health'}
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
              {(['plan', 'findings', 'keywords', 'history', 'report'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setDetailTab(t)}
                  className={clsx(
                    'px-3 py-1.5 text-sm font-medium border-b-2 -mb-px',
                    detailTab === t ? 'border-brand-600 text-brand-600' : 'border-transparent text-slate-500',
                  )}
                >
                  {t === 'plan'
                    ? 'Action Plan'
                    : t === 'findings'
                    ? 'All Findings'
                    : t === 'keywords'
                    ? 'Keyword Ideas'
                    : t === 'history'
                    ? 'History'
                    : 'Report'}
                </button>
              ))}
            </div>
            {/* One button prints the FULL report (all five sections below,
                via PrintableAuditReport) regardless of which tab is active
                on screen -- see that component's own docstring for why a
                per-tab print button couldn't do this. */}
            <Button size="sm" variant="secondary" className="mb-2" onClick={() => window.print()}>
              Print Full Report (PDF)
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

// Stage 1 of the SEO Audit & Optimization upgrade (see apps/agents/
// seo-audit/CLAUDE.md) -- register websites to audit. Audit runs,
// findings, and recommendations land in later stages of that same plan.
function WebsitesTab() {
  const qc = useQueryClient()
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
      <Card title="Add a website to audit" className="print:hidden">
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
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
          />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <input
              placeholder="Name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-base"
            />
            <input
              placeholder="Target country (optional)"
              value={targetCountry}
              onChange={(e) => setTargetCountry(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-base"
            />
            <input
              placeholder="Target language (optional)"
              value={targetLanguage}
              onChange={(e) => setTargetLanguage(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-base"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm text-slate-500">Crawl depth</label>
            <select
              value={crawlTier}
              onChange={(e) => setCrawlTier(e.target.value as typeof crawlTier)}
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-base"
            >
              <option value="starter">Starter (25 pages)</option>
              <option value="standard">Standard (100 pages)</option>
              <option value="advanced">Advanced (500 pages)</option>
            </select>
          </div>
          <Button type="submit" size="sm" loading={createMut.isPending} disabled={!url}>
            Add website
          </Button>
          {createMut.isError && (
            <p className="text-sm text-red-600">
              Couldn't add that website. Check the URL and your account's website limit.
            </p>
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
            No websites registered yet. Add one above to start an SEO audit.
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
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wide">Live now</p>
          <p className="mt-1 text-base text-slate-600">{product.description || '(no description)'}</p>
          <p className="mt-2 text-sm text-slate-400">SEO title: {product.seo_title || '-'}</p>
          <p className="text-sm text-slate-400">Meta: {product.meta_description || '-'}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-brand-600 uppercase tracking-wide">Draft</p>
          <p className="mt-1 text-base text-slate-900">{draft.draft_description || '-'}</p>
          <p className="mt-2 text-sm text-slate-600">SEO title: {draft.draft_seo_title || '-'}</p>
          <p className="text-sm text-slate-600">Meta: {draft.draft_meta_description || '-'}</p>
        </div>
      </div>

      <div className="mt-4 flex gap-2">
        <Button size="sm" loading={approveMut.isPending} onClick={() => approveMut.mutate()}>
          <Check size={16} className="mr-1" />
          Approve
        </Button>
        <Button size="sm" variant="secondary" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
          <X size={16} className="mr-1" />
          Reject
        </Button>
      </div>
    </Card>
  )
}

function ContentTab() {
  const qc = useQueryClient()
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
      <Card title="Pick products to (re)generate">
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
          {products.length === 0 && <p className="text-base text-slate-400">Add products first.</p>}
        </div>
        <Button
          className="mt-4"
          size="sm"
          disabled={selected.size === 0}
          loading={generateMut.isPending}
          onClick={() => generateMut.mutate()}
        >
          <Sparkles size={16} className="mr-1" />
          Generate drafts ({selected.size})
        </Button>
        {generateMut.isError && (
          <p className="mt-2 text-sm text-red-600">Something went wrong generating drafts. Please try again.</p>
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
            No drafts waiting for review. Pick some products above and generate a batch.
          </div>
        )}
      </div>
    </div>
  )
}

// Two-tier pricing card, same visual language as PlanPage.tsx's chat-widget
// plan cards (brand-gradient "Most Popular" card for the paid tier) so the
// two pricing surfaces in this app don't look like two different products.
function SeoTierCard({ tier, isCurrent }: { tier: AgentTier; isCurrent: boolean }) {
  const navigate = useNavigate()
  const isFree = tier.key === 'free'
  const priceLabel = isFree
    ? 'Free'
    : tier.price_nok !== null
      ? formatCurrency(tier.price_nok, 'NOK')
      : formatCurrency(tier.price_usd, 'USD')

  return (
    <div
      className={clsx(
        'flex flex-col rounded-2xl border p-6 print:break-inside-avoid print:border-slate-300',
        !isFree ? 'brand-gradient text-white shadow-sm shadow-brand-200 print:bg-none print:text-slate-900' : 'bg-white border-slate-300',
      )}
    >
      {!isFree && (
        <span className="mb-2 inline-flex w-fit items-center gap-1 rounded-full bg-white/20 px-2.5 py-1 text-sm font-semibold print:border print:border-slate-300 print:bg-transparent print:text-slate-700">
          <Star size={12} /> Most Popular
        </span>
      )}
      <h3 className={clsx('text-xl font-bold', !isFree ? 'text-white print:text-slate-900' : 'text-slate-900')}>{tier.name}</h3>
      <p className={clsx('text-sm mt-1', !isFree ? 'text-brand-50 print:text-slate-500' : 'text-slate-500')}>{tier.tagline}</p>
      <p className="mt-4">
        <span className={clsx('text-3xl font-bold', !isFree ? 'text-white print:text-slate-900' : 'text-slate-900')}>{priceLabel}</span>
        {!isFree && <span className={clsx('text-sm', !isFree ? 'text-brand-50 print:text-slate-500' : 'text-slate-500')}> one-time</span>}
      </p>

      <Button
        className="mt-4 w-full justify-center print:hidden"
        variant={!isFree ? 'secondary' : isCurrent ? 'secondary' : 'primary'}
        disabled={isCurrent}
        onClick={() => navigate('/dashboard/plan')}
      >
        {isCurrent ? 'Current plan' : isFree ? 'Contact us to activate' : 'Contact us to upgrade'}
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
  const seo = catalog?.find((a) => a.key === 'seo_audit_optimization')

  if (!seo?.tiers) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 print:hidden">
        <p className="text-base text-slate-500 max-w-2xl">
          SEO Audit &amp; Optimization is sold in two tiers. Professional adds a deeper,
          Screaming-Frog-style crawler on top of everything in the free tier — items marked
          "(coming soon)" are priced in but not built yet.
        </p>
        <Button size="sm" variant="secondary" onClick={() => window.print()}>
          Print / Save as PDF
        </Button>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {seo.tiers.map((tier) => (
          <SeoTierCard key={tier.key} tier={tier} isCurrent={tier.key === 'free' && !!access?.seo_audit_optimization} />
        ))}
      </div>
    </div>
  )
}

const TABS = [
  { key: 'websites', label: 'Websites' },
  { key: 'content', label: 'Content' },
  { key: 'plans', label: 'Plans' },
] as const

export function SeoPage() {
  const { data: access, isLoading } = useAgentAccess()
  const [tab, setTab] = useState<(typeof TABS)[number]['key']>('websites')
  if (isLoading) return null

  if (!access?.seo_audit_optimization) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">SEO</h1>
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
        <h1 className="text-4xl font-bold text-slate-900">SEO</h1>
        <p className="text-base text-slate-500 mt-1">
          Audit your websites for real, deterministic SEO issues, and fix them with AI-generated
          copy you review before anything goes live.
        </p>
      </div>

      <div className="flex gap-2 border-b border-slate-200 print:hidden">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'px-4 py-2 text-base font-medium border-b-2 -mb-px transition-colors',
              tab === t.key
                ? 'border-brand-600 text-brand-600'
                : 'border-transparent text-slate-500 hover:text-slate-700',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'websites' ? <WebsitesTab /> : tab === 'content' ? <ContentTab /> : <PlansTab />}
    </div>
  )
}
