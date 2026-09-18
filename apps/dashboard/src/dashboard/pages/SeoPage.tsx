import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Check, X, Trash2, Globe, PlayCircle } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { AgentGate } from '../../shared/components/AgentGate'
import { useAgentAccess } from '../../shared/hooks/usePlan'

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
// signal (see apps/agents/seo-copywriter/CLAUDE.md, Phase 10).
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

      <div className="flex flex-wrap gap-2">
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

      {audit.executive_summary && (
        <p className="rounded-lg bg-white p-3 text-sm text-slate-700 border border-slate-200">
          {audit.executive_summary}
        </p>
      )}
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
                <div key={item.rule_code} className={clsx('rounded-lg border px-3 py-2', item.status === 'ignored' && 'opacity-50')}>
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
        <div key={f.id} className={clsx('rounded-lg border px-3 py-2', f.status === 'ignored' ? 'opacity-50 border-slate-100' : 'border-slate-200')}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className={clsx('mr-2 rounded-full px-2 py-0.5 text-xs font-medium uppercase', SEVERITY_COLORS[f.severity])}>
                {f.severity}
              </span>
              <span className="font-medium text-slate-800">{f.issue}</span>
              {f.affected_url && <p className="mt-1 text-sm text-slate-500 break-all">{f.affected_url}</p>}
              {f.explanation && <p className="mt-1 text-sm text-slate-500">{f.explanation}</p>}
              {f.recommended_fix && <p className="mt-1 text-sm text-slate-700">Fix: {f.recommended_fix}</p>}
            </div>
            {f.status !== 'ignored' && (
              <Button size="sm" variant="ghost" loading={ignoreMut.isPending} onClick={() => ignoreMut.mutate(f.id)}>
                Ignore
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// Stage 2 of the SEO Audit & Optimization upgrade (see apps/agents/
// seo-copywriter/CLAUDE.md) -- crawl a registered website and store
// per-page facts. Findings/health scores/recommendations are later stages
// of that same plan; this is just "run a crawl and see it finish".
function WebsiteCard({ website, onDelete, deleting }: { website: SeoWebsite; onDelete: () => void; deleting: boolean }) {
  const qc = useQueryClient()
  const [showFindings, setShowFindings] = useState(false)
  const [severityFilter, setSeverityFilter] = useState<Severity | null>(null)
  const [detailTab, setDetailTab] = useState<'findings' | 'plan'>('plan')
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
    <Card>
      <div className="flex items-start justify-between gap-4">
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
        <div className="mt-4 flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm">
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
          <SeoHealthPanel audit={latestAudit} severityFilter={severityFilter} onSeverityFilter={setSeverityFilter} />
          <div className="mt-3 flex gap-2 border-b border-slate-200">
            {(['plan', 'findings'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setDetailTab(t)}
                className={clsx(
                  'px-3 py-1.5 text-sm font-medium border-b-2 -mb-px',
                  detailTab === t ? 'border-brand-600 text-brand-600' : 'border-transparent text-slate-500',
                )}
              >
                {t === 'plan' ? 'Action Plan' : 'All Findings'}
              </button>
            ))}
          </div>
          <div className="mt-3">
            {detailTab === 'plan' ? (
              <ActionPlanList auditId={latestAudit.id} />
            ) : (
              <FindingsList auditId={latestAudit.id} severityFilter={severityFilter} />
            )}
          </div>
        </>
      )}
    </Card>
  )
}

// Stage 1 of the SEO Audit & Optimization upgrade (see apps/agents/
// seo-copywriter/CLAUDE.md) -- register websites to audit. Audit runs,
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
      <Card title="Add a website to audit">
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
  product_id: string
  draft_description: string
  draft_seo_title: string
  draft_meta_description: string
  status: 'draft' | 'approved' | 'rejected'
}

// Only ever "generate for products I picked, review, approve/reject" -- see
// apps/agents/seo-copywriter/CLAUDE.md: silently overwriting live product
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
          <p className="mt-1 text-base text-slate-900">{draft.draft_description}</p>
          <p className="mt-2 text-sm text-slate-600">SEO title: {draft.draft_seo_title}</p>
          <p className="text-sm text-slate-600">Meta: {draft.draft_meta_description}</p>
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

const TABS = [
  { key: 'websites', label: 'Websites' },
  { key: 'content', label: 'Content' },
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
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">SEO</h1>
        <p className="text-base text-slate-500 mt-1">
          Audit your websites for real, deterministic SEO issues, and fix them with AI-generated
          copy you review before anything goes live.
        </p>
      </div>

      <div className="flex gap-2 border-b border-slate-200">
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

      {tab === 'websites' ? <WebsitesTab /> : <ContentTab />}
    </div>
  )
}
