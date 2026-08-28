import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft } from 'lucide-react'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'

interface BookingListItem {
  id: string
  name: string
  email: string
  phone: string | null
  meeting_type: string
  start_at: string
  end_at: string
  status: string
  created_at: string
}

interface BookingListOut {
  items: BookingListItem[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 20

// No business_id yet on Booking (see app/models/booking.py's own comment)
// -- these are all Mielikkix's own demo-calendar bookings, not a real
// tenant's, so there's no per-tenant dashboard this belongs in yet. Lives
// here, read-only, until per-tenant OAuth/booking exists (Phase 5, see
// apps/agents/booking-assistant/CLAUDE.md).
export function AdminBookingsPage() {
  const [page, setPage] = useState(1)

  const { data } = useQuery<BookingListOut>({
    queryKey: ['admin', 'bookings', page],
    queryFn: () =>
      api.get('/admin/bookings', { params: { page, page_size: PAGE_SIZE } }).then((r) => r.data),
    placeholderData: (prev) => prev,
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Bookings</h1>
        <p className="text-base text-slate-500 mt-1">
          Every booking made through Booking Assistant's demo calendar (not yet per-tenant — see
          Booking Assistant's own docs).
        </p>
      </div>

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-base">
            <thead>
              <tr className="border-b border-slate-100 text-sm text-slate-500">
                <th className="px-6 py-3 font-medium">Name</th>
                <th className="px-6 py-3 font-medium">Email</th>
                <th className="px-6 py-3 font-medium">Meeting type</th>
                <th className="px-6 py-3 font-medium">When</th>
                <th className="px-6 py-3 font-medium">Booked</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((b) => (
                <tr key={b.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                  <td className="px-6 py-4 font-semibold text-slate-900">{b.name}</td>
                  <td className="px-6 py-4 text-slate-700">{b.email}</td>
                  <td className="px-6 py-4 text-slate-700 capitalize">{b.meeting_type}</td>
                  <td className="px-6 py-4 text-sm text-slate-500">
                    {new Date(b.start_at).toLocaleString(undefined, {
                      dateStyle: 'medium',
                      timeStyle: 'short',
                    })}
                    {' – '}
                    {new Date(b.end_at).toLocaleTimeString(undefined, { timeStyle: 'short' })}
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500">
                    {new Date(b.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-slate-400">
                    No bookings yet.
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
            Page {data.page} of {totalPages} · {data.total} bookings
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
