import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Search, ChevronRight, ChevronLeft } from 'lucide-react'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { Input } from '../../../shared/components/Input'
import { clsx } from 'clsx'

interface BusinessListItem {
  id: string
  name: string
  slug: string
  industry: string
  plan: string
  plan_name: string
  status: string
  owner_email: string | null
  owner_name: string | null
  created_at: string
  websites: number
  conversations_this_month: number
  documents: number
  products: number
}

interface BusinessListOut {
  items: BusinessListItem[]
  total: number
  page: number
  page_size: number
}

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-slate-100 text-slate-600',
  basic: 'bg-blue-100 text-blue-700',
  business: 'bg-violet-100 text-violet-700',
  growth: 'bg-emerald-100 text-emerald-700',
}
const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  trial: 'bg-amber-100 text-amber-700',
  suspended: 'bg-red-100 text-red-700',
}

const PAGE_SIZE = 20

export function AdminBusinessesPage() {
  const [q, setQ] = useState('')
  const [plan, setPlan] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const { data } = useQuery<BusinessListOut>({
    queryKey: ['admin', 'businesses', q, plan, status, page],
    queryFn: () =>
      api
        .get('/admin/businesses', {
          params: { q: q || undefined, plan: plan || undefined, status: status || undefined, page, page_size: PAGE_SIZE },
        })
        .then((r) => r.data),
    placeholderData: (prev) => prev,
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Businesses</h1>
        <p className="text-base text-slate-500 mt-1">Every business registered on MielikkiX.</p>
      </div>

      <Card>
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[14rem]">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Search name, slug, or owner email"
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1) }}
              className="pl-9"
            />
          </div>
          <select
            value={plan}
            onChange={(e) => { setPlan(e.target.value); setPage(1) }}
            className="rounded-xl border border-slate-300 px-3 py-2 text-base shadow-sm outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
          >
            <option value="">All plans</option>
            <option value="free">Free</option>
            <option value="basic">Basic</option>
            <option value="business">Business</option>
            <option value="growth">Growth</option>
          </select>
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1) }}
            className="rounded-xl border border-slate-300 px-3 py-2 text-base shadow-sm outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="trial">Trial</option>
            <option value="suspended">Suspended</option>
          </select>
        </div>
      </Card>

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-base">
            <thead>
              <tr className="border-b border-slate-100 text-sm text-slate-500">
                <th className="px-6 py-3 font-medium">Business</th>
                <th className="px-6 py-3 font-medium">Owner</th>
                <th className="px-6 py-3 font-medium">Plan</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Usage</th>
                <th className="px-6 py-3 font-medium">Joined</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody>
              {data?.items.map((b) => (
                <tr key={b.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                  <td className="px-6 py-4">
                    <p className="font-semibold text-slate-900">{b.name}</p>
                    <p className="text-sm text-slate-400">{b.slug} · {b.industry}</p>
                  </td>
                  <td className="px-6 py-4">
                    <p className="text-slate-700">{b.owner_name ?? '—'}</p>
                    <p className="text-sm text-slate-400">{b.owner_email ?? '—'}</p>
                  </td>
                  <td className="px-6 py-4">
                    <span className={clsx('text-sm px-2 py-1 rounded-full font-medium capitalize', PLAN_COLORS[b.plan] || PLAN_COLORS.free)}>
                      {b.plan_name}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className={clsx('text-sm px-2 py-1 rounded-full font-medium capitalize', STATUS_COLORS[b.status] || STATUS_COLORS.trial)}>
                      {b.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500">
                    {b.conversations_this_month} conv · {b.documents} docs · {b.products} products
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500">{new Date(b.created_at).toLocaleDateString()}</td>
                  <td className="px-6 py-4 text-right">
                    <Link to={`/admin/businesses/${b.id}`} className="text-brand-600 hover:text-brand-700">
                      <ChevronRight size={18} />
                    </Link>
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-400">No businesses match your filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-base text-slate-500">
          <span>Page {data.page} of {totalPages} · {data.total} businesses</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50"
            >
              <ChevronLeft size={16} /> Prev
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50"
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
