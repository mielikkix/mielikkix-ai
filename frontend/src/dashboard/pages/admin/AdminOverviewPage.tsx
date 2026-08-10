import { useQuery } from '@tanstack/react-query'
import { Building2, MessageSquare, Users, FileText } from 'lucide-react'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { MiniBarChart } from '../../components/admin/MiniBarChart'

interface Overview {
  total_businesses: number
  businesses_by_plan: Record<string, number>
  businesses_by_status: Record<string, number>
  signups_last_30d: { date: string; count: number }[]
  total_conversations: number
  total_leads: number
  total_documents: number
}

const PLAN_ORDER = ['free', 'basic', 'business', 'growth']

function formatDay(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function AdminOverviewPage() {
  const { data } = useQuery<Overview>({
    queryKey: ['admin', 'overview'],
    queryFn: () => api.get('/admin/overview').then((r) => r.data),
  })

  const stats = [
    { label: 'Registered businesses', value: data?.total_businesses, icon: Building2, bg: 'bg-violet-100', fg: 'text-violet-600' },
    { label: 'Total conversations', value: data?.total_conversations, icon: MessageSquare, bg: 'bg-blue-100', fg: 'text-blue-600' },
    { label: 'Total leads', value: data?.total_leads, icon: Users, bg: 'bg-emerald-100', fg: 'text-emerald-600' },
    { label: 'Documents uploaded', value: data?.total_documents, icon: FileText, bg: 'bg-amber-100', fg: 'text-amber-600' },
  ]

  const chartData = (data?.signups_last_30d ?? []).map((d) => ({ label: formatDay(d.date), value: d.count }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Platform Overview</h1>
        <p className="text-base text-slate-500 mt-1">A snapshot of every business on AgentNexus.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map(({ label, value, icon: Icon, bg, fg }) => (
          <Card key={label}>
            <div className="flex items-center gap-4">
              <div className={`grid h-12 w-12 flex-shrink-0 place-items-center rounded-xl ${bg}`}>
                <Icon className={fg} size={22} />
              </div>
              <div>
                <p className="text-3xl font-bold text-slate-900">{value ?? '—'}</p>
                <p className="text-base text-slate-500">{label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card title="Signups, last 30 days">
        <MiniBarChart data={chartData} emptyMessage="No signups in the last 30 days." />
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="Businesses by plan">
          <div className="space-y-2">
            {PLAN_ORDER.filter((p) => data?.businesses_by_plan?.[p]).map((plan) => (
              <div key={plan} className="flex items-center justify-between text-base">
                <span className="capitalize text-slate-600">{plan}</span>
                <span className="font-semibold text-slate-900">{data?.businesses_by_plan[plan]}</span>
              </div>
            ))}
            {data && Object.keys(data.businesses_by_plan).length === 0 && (
              <p className="text-sm text-slate-400">No businesses yet.</p>
            )}
          </div>
        </Card>
        <Card title="Businesses by status">
          <div className="space-y-2">
            {Object.entries(data?.businesses_by_status ?? {}).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between text-base">
                <span className="capitalize text-slate-600">{status}</span>
                <span className="font-semibold text-slate-900">{count}</span>
              </div>
            ))}
            {data && Object.keys(data.businesses_by_status).length === 0 && (
              <p className="text-sm text-slate-400">No businesses yet.</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
