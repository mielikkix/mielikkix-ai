import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Gauge, Ban, PlayCircle, TriangleAlert, CreditCard } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'

const PLAN_OPTIONS = [
  { key: 'free', label: 'Free' },
  { key: 'basic', label: 'Basic' },
  { key: 'business', label: 'Business' },
  { key: 'growth', label: 'Growth' },
]

interface Owner {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
}

interface BusinessDetail {
  id: string
  name: string
  slug: string
  industry: string
  logo_url: string | null
  primary_color: string
  plan: string
  plan_name: string
  status: string
  api_access_addon: boolean
  created_at: string
  updated_at: string
  settings: {
    tone: string
    llm_provider: string
    llm_model: string | null
    languages: string[]
    contact_email: string | null
    contact_phone: string | null
  } | null
  owners: Owner[]
  plan_limits: Record<string, number | null>
  usage: Record<string, number>
  features: Record<string, boolean | string>
  faqs: number
  leads: number
  conversations_total: number
  llm_usage_30d: { requests: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }
}

function limitLine(label: string, used: number, limit: number | null) {
  return (
    <div key={label} className="flex items-center justify-between text-base">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{used} / {limit ?? '∞'}</span>
    </div>
  )
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  trial: 'bg-amber-100 text-amber-700',
  suspended: 'bg-red-100 text-red-700',
}

export function AdminBusinessDetailPage() {
  const { businessId } = useParams<{ businessId: string }>()
  const qc = useQueryClient()
  const [confirmingSuspend, setConfirmingSuspend] = useState(false)
  const [pendingPlan, setPendingPlan] = useState<string | null>(null)

  const { data } = useQuery<BusinessDetail>({
    queryKey: ['admin', 'business', businessId],
    queryFn: () => api.get(`/admin/businesses/${businessId}`).then((r) => r.data),
    enabled: !!businessId,
  })

  const invalidateAfterChange = (updated: BusinessDetail) => {
    qc.setQueryData(['admin', 'business', businessId], updated)
    qc.invalidateQueries({ queryKey: ['admin', 'businesses'] })
    qc.invalidateQueries({ queryKey: ['admin', 'overview'] })
  }

  const statusMut = useMutation({
    mutationFn: (status: 'active' | 'suspended') =>
      api.patch(`/admin/businesses/${businessId}/status`, { status }).then((r) => r.data),
    onSuccess: (updated: BusinessDetail) => {
      invalidateAfterChange(updated)
      setConfirmingSuspend(false)
    },
  })

  const planMut = useMutation({
    mutationFn: (plan: string) => api.patch(`/admin/businesses/${businessId}/plan`, { plan }).then((r) => r.data),
    onSuccess: (updated: BusinessDetail) => {
      invalidateAfterChange(updated)
      setPendingPlan(null)
    },
  })

  if (!data) return null

  return (
    <div className="space-y-6">
      <Link to="/admin/businesses" className="inline-flex items-center gap-1 text-base text-slate-500 hover:text-slate-700">
        <ArrowLeft size={16} /> Back to businesses
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">{data.name}</h1>
          <p className="text-base text-slate-500 mt-1">{data.slug} · {data.industry} · joined {new Date(data.created_at).toLocaleDateString()}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm px-3 py-1.5 rounded-full font-medium bg-violet-100 text-violet-700 capitalize">{data.plan_name}</span>
          <select
            value=""
            onChange={(e) => { if (e.target.value) setPendingPlan(e.target.value) }}
            className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-600 outline-none focus:border-brand-500"
            aria-label="Set plan"
          >
            <option value="">Set plan…</option>
            {PLAN_OPTIONS.filter((p) => p.key !== data.plan).map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
          <span className={clsx('text-sm px-3 py-1.5 rounded-full font-medium capitalize', STATUS_COLORS[data.status] || STATUS_COLORS.trial)}>
            {data.status}
          </span>
          {data.status === 'suspended' ? (
            <Button size="sm" variant="secondary" loading={statusMut.isPending} onClick={() => statusMut.mutate('active')}>
              <PlayCircle size={15} className="mr-1.5" /> Reactivate
            </Button>
          ) : (
            <Button size="sm" variant="danger" onClick={() => setConfirmingSuspend(true)}>
              <Ban size={15} className="mr-1.5" /> Suspend
            </Button>
          )}
        </div>
      </div>

      {confirmingSuspend && (
        <Card className="!border-red-200 !bg-red-50">
          <div className="flex flex-wrap items-center gap-3">
            <TriangleAlert size={20} className="flex-shrink-0 text-red-500" />
            <p className="flex-1 text-base text-red-800">
              Suspending <span className="font-semibold">{data.name}</span> will also drop them to the Free plan.
              This mirrors what a failed/cancelled payment would do — there's no real billing wired up yet, so this is manual.
            </p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setConfirmingSuspend(false)}>Cancel</Button>
              <Button size="sm" variant="danger" loading={statusMut.isPending} onClick={() => statusMut.mutate('suspended')}>
                Confirm suspend
              </Button>
            </div>
          </div>
        </Card>
      )}

      {pendingPlan && (
        <Card className="!border-brand-200 !bg-brand-50">
          <div className="flex flex-wrap items-center gap-3">
            <CreditCard size={20} className="flex-shrink-0 text-brand-600" />
            <p className="flex-1 text-base text-brand-900">
              Manually set <span className="font-semibold">{data.name}</span>'s plan to{' '}
              <span className="font-semibold capitalize">{pendingPlan}</span>? No payment is being taken — self-serve
              upgrades are Free-only until a real payment processor is connected, so this is the only way a business
              gets a paid plan today.
              {pendingPlan !== 'free' && data.status !== 'suspended' && ' Status will be set to Active.'}
              {pendingPlan === 'free' && data.status !== 'suspended' && ' Status will be set to Trial.'}
            </p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setPendingPlan(null)}>Cancel</Button>
              <Button size="sm" loading={planMut.isPending} onClick={() => planMut.mutate(pendingPlan)}>
                Confirm plan change
              </Button>
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Owners">
          <div className="space-y-3">
            {data.owners.map((o) => (
              <div key={o.id} className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-slate-800">{o.full_name}</p>
                  <p className="text-sm text-slate-400">{o.email}</p>
                </div>
                <span className={clsx('text-sm px-2 py-1 rounded-full font-medium capitalize', o.role === 'owner' ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-600')}>
                  {o.role}
                </span>
              </div>
            ))}
            {data.owners.length === 0 && <p className="text-sm text-slate-400">No users found.</p>}
          </div>
        </Card>

        <Card title="Chatbot settings">
          {data.settings ? (
            <div className="space-y-2 text-base">
              <div className="flex justify-between"><span className="text-slate-500">LLM provider</span><span className="font-medium text-slate-800">{data.settings.llm_provider}{data.settings.llm_model ? ` (${data.settings.llm_model})` : ''}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Tone</span><span className="font-medium text-slate-800 capitalize">{data.settings.tone}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Languages</span><span className="font-medium text-slate-800">{data.settings.languages.join(', ')}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Contact email</span><span className="font-medium text-slate-800">{data.settings.contact_email ?? '—'}</span></div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">No settings configured yet.</p>
          )}
        </Card>

        <Card title="Plan usage">
          <div className="space-y-2">
            {limitLine('Websites', data.usage.websites, data.plan_limits.max_websites)}
            {limitLine('Conversations this month', data.usage.conversations_this_month, data.plan_limits.max_conversations_per_month)}
            {limitLine('Documents', data.usage.documents, data.plan_limits.max_document_uploads)}
            {limitLine('Products', data.usage.products, data.plan_limits.max_products)}
          </div>
        </Card>

        <Card title="Resource counts">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <p className="text-2xl font-bold text-slate-900">{data.faqs}</p>
              <p className="text-sm text-slate-500">FAQs</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{data.leads}</p>
              <p className="text-sm text-slate-500">Leads</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{data.conversations_total}</p>
              <p className="text-sm text-slate-500">Conversations (all-time)</p>
            </div>
          </div>
        </Card>
      </div>

      <Card title="Groq usage — last 30 days">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <div><p className="text-2xl font-bold text-slate-900">{data.llm_usage_30d.requests}</p><p className="text-sm text-slate-500">Requests</p></div>
            <div><p className="text-2xl font-bold text-slate-900">{data.llm_usage_30d.prompt_tokens.toLocaleString()}</p><p className="text-sm text-slate-500">Prompt tokens</p></div>
            <div><p className="text-2xl font-bold text-slate-900">{data.llm_usage_30d.completion_tokens.toLocaleString()}</p><p className="text-sm text-slate-500">Completion tokens</p></div>
            <div><p className="text-2xl font-bold text-slate-900">{data.llm_usage_30d.total_tokens.toLocaleString()}</p><p className="text-sm text-slate-500">Total tokens</p></div>
          </div>
          <Link
            to={`/admin/usage?business_id=${data.id}`}
            className="flex items-center gap-1 text-base font-semibold text-brand-600 hover:underline"
          >
            <Gauge size={16} /> View full usage
          </Link>
        </div>
      </Card>
    </div>
  )
}
