import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Zap, Hash, ArrowRightLeft, Layers, X } from 'lucide-react'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { MiniBarChart } from '../../components/admin/MiniBarChart'

interface LLMUsage {
  totals: { requests: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }
  by_day: { date: string; requests: number; total_tokens: number }[]
  by_business: { business_id: string; business_name: string; requests: number; total_tokens: number }[]
}

const RANGES = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
]

function formatDay(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function AdminUsagePage() {
  const [days, setDays] = useState(30)
  const [searchParams, setSearchParams] = useSearchParams()
  const businessId = searchParams.get('business_id')

  const { data } = useQuery<LLMUsage>({
    queryKey: ['admin', 'llm-usage', businessId, days],
    queryFn: () =>
      api
        .get('/admin/llm-usage', { params: { business_id: businessId || undefined, days } })
        .then((r) => r.data),
  })

  const stats = [
    { label: 'Requests', value: data?.totals.requests, icon: Hash },
    { label: 'Prompt tokens', value: data?.totals.prompt_tokens, icon: ArrowRightLeft },
    { label: 'Completion tokens', value: data?.totals.completion_tokens, icon: Layers },
    { label: 'Total tokens', value: data?.totals.total_tokens, icon: Zap },
  ]

  const chartData = (data?.by_day ?? []).map((d) => ({ label: formatDay(d.date), value: d.total_tokens }))
  const businessName = data?.by_business.find((b) => b.business_id === businessId)?.business_name

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">Groq API Usage</h1>
          <p className="text-base text-slate-500 mt-1">
            Token usage recorded for the Groq LLM provider{businessName ? <> for <span className="font-semibold text-slate-700">{businessName}</span></> : ' across all businesses'}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {businessId && (
            <button
              onClick={() => setSearchParams({})}
              className="flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <X size={14} /> Clear filter
            </button>
          )}
          <div className="flex rounded-xl border border-slate-300 bg-white p-1">
            {RANGES.map((r) => (
              <button
                key={r.days}
                onClick={() => setDays(r.days)}
                className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${days === r.days ? 'brand-gradient text-white' : 'text-slate-600 hover:bg-slate-50'}`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map(({ label, value, icon: Icon }) => (
          <Card key={label}>
            <div className="flex items-center gap-4">
              <div className="grid h-12 w-12 flex-shrink-0 place-items-center rounded-xl bg-brand-100">
                <Icon className="text-brand-600" size={20} />
              </div>
              <div>
                <p className="text-3xl font-bold text-slate-900">{value?.toLocaleString() ?? '—'}</p>
                <p className="text-base text-slate-500">{label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card title={`Total tokens per day, last ${days} days`}>
        <MiniBarChart data={chartData} emptyMessage="No Groq usage recorded in this range." />
      </Card>

      {!businessId && (
        <Card title="Top businesses by token usage">
          <div className="space-y-3">
            {data?.by_business.map((b) => (
              <div key={b.business_id} className="flex items-center justify-between gap-3">
                <Link to={`/admin/businesses/${b.business_id}`} className="text-slate-800 font-medium hover:text-brand-600">
                  {b.business_name}
                </Link>
                <span className="text-sm text-slate-500">{b.requests} requests · {b.total_tokens.toLocaleString()} tokens</span>
              </div>
            ))}
            {data && data.by_business.length === 0 && <p className="text-sm text-slate-400">No usage recorded yet.</p>}
          </div>
        </Card>
      )}
    </div>
  )
}
