import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'

interface TicketListItem {
  id: string
  channel: string
  status: string
  category: string | null
  priority: string | null
  confidence: number | null
  customer_name: string | null
  customer_email: string | null
  customer_phone: string | null
  created_at: string
  updated_at: string
}

interface TicketListOut {
  items: TicketListItem[]
  total: number
  page: number
  page_size: number
}

interface TicketDetail extends TicketListItem {
  messages: { role: string; content: string; created_at: string }[]
}

const PAGE_SIZE = 20

const STATUS_STYLES: Record<string, string> = {
  escalated: 'bg-red-50 text-red-700',
  open: 'bg-emerald-50 text-emerald-700',
  resolved: 'bg-slate-200 text-slate-600',
}

const PRIORITY_STYLES: Record<string, string> = {
  urgent: 'bg-red-50 text-red-700',
  high: 'bg-amber-50 text-amber-700',
  medium: 'bg-blue-50 text-blue-700',
  low: 'bg-slate-100 text-slate-500',
}

function Pill({ text, styles }: { text: string; styles: Record<string, string> }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
        styles[text] ?? 'bg-slate-100 text-slate-500'
      }`}
    >
      {text}
    </span>
  )
}

function TicketDetailRow({ ticketId }: { ticketId: string }) {
  const { data } = useQuery<TicketDetail>({
    queryKey: ['admin', 'ticket', ticketId],
    queryFn: () => api.get(`/admin/tickets/${ticketId}`).then((r) => r.data),
  })

  return (
    <tr className="bg-slate-50">
      <td colSpan={7} className="px-6 py-4">
        {!data ? (
          <p className="text-sm text-slate-400">Loading conversation...</p>
        ) : data.messages.length === 0 ? (
          <p className="text-sm text-slate-400">No messages recorded for this ticket.</p>
        ) : (
          <div className="space-y-2">
            {data.messages.map((m, i) => (
              <div key={i} className="flex gap-2 text-sm">
                <span className="w-16 flex-shrink-0 font-semibold capitalize text-slate-500">{m.role}:</span>
                <span className="text-slate-700">{m.content}</span>
              </div>
            ))}
          </div>
        )}
      </td>
    </tr>
  )
}

// Same "no business_id" reasoning as AdminBookingsPage -- Support Triage's
// tickets belong to the platform itself (mielikkix.ai's own visitors), not
// a tenant, so this inbox lives in platform admin, not a per-tenant page.
// See apps/agents/support-triage/CLAUDE.md, "Dashboard module".
export function AdminTicketsPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data } = useQuery<TicketListOut>({
    queryKey: ['admin', 'tickets', page, statusFilter],
    queryFn: () =>
      api
        .get('/admin/tickets', { params: { page, page_size: PAGE_SIZE, status: statusFilter || undefined } })
        .then((r) => r.data),
    placeholderData: (prev) => prev,
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">Support Tickets</h1>
          <p className="text-base text-slate-500 mt-1">
            Conversations from the website chat widget and Voice Receptionist handoffs that need a human's
            attention, or were answered automatically.
          </p>
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="escalated">Escalated</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-base">
            <thead>
              <tr className="border-b border-slate-100 text-sm text-slate-500">
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Channel</th>
                <th className="px-6 py-3 font-medium">Category</th>
                <th className="px-6 py-3 font-medium">Priority</th>
                <th className="px-6 py-3 font-medium">Contact</th>
                <th className="px-6 py-3 font-medium">Created</th>
                <th className="px-6 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((t) => (
                <>
                  <tr
                    key={t.id}
                    className="cursor-pointer border-b border-slate-50 last:border-0 hover:bg-slate-50"
                    onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                  >
                    <td className="px-6 py-4">
                      <Pill text={t.status} styles={STATUS_STYLES} />
                    </td>
                    <td className="px-6 py-4 text-slate-700 capitalize">{t.channel}</td>
                    <td className="px-6 py-4 text-slate-700 capitalize">{t.category ?? '-'}</td>
                    <td className="px-6 py-4">
                      {t.priority ? <Pill text={t.priority} styles={PRIORITY_STYLES} /> : '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-500">
                      {t.customer_name ?? t.customer_email ?? t.customer_phone ?? '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-500">
                      {new Date(t.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                    </td>
                    <td className="px-6 py-4 text-slate-400">
                      {expandedId === t.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </td>
                  </tr>
                  {expandedId === t.id && <TicketDetailRow key={`${t.id}-detail`} ticketId={t.id} />}
                </>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-400">
                    No tickets yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-base text-slate-500">
          <span>
            Page {data.page} of {totalPages} · {data.total} tickets
          </span>
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
