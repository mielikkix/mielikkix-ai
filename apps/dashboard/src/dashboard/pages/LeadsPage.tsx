import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { clsx } from 'clsx'
import { MoreVertical } from 'lucide-react'

interface Lead {
  id: string
  name: string
  email: string | null
  phone: string | null
  message: string | null
  status: string
  created_at: string
}

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  contacted: 'bg-yellow-100 text-yellow-700',
  won: 'bg-green-100 text-green-700',
  lost: 'bg-slate-100 text-slate-500',
}
const STATUSES = ['new', 'contacted', 'won', 'lost']

export function LeadsPage() {
  const qc = useQueryClient()
  const { data: leads = [] } = useQuery<Lead[]>({
    queryKey: ['leads'],
    queryFn: () => api.get('/leads').then((r) => r.data),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patch(`/leads/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })

  const [menuOpen, setMenuOpen] = useState<string | null>(null)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Leads</h1>
        <p className="text-base text-slate-500 mt-1">Contacts captured by your chatbot.</p>
      </div>

      <div className="space-y-3">
        {leads.map((lead) => (
          <Card key={lead.id}>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <p className="font-semibold text-slate-900">{lead.name}</p>
                <div className="flex gap-3 mt-1 text-sm text-slate-500 flex-wrap">
                  {lead.email && <span>{lead.email}</span>}
                  {lead.phone && <span>{lead.phone}</span>}
                </div>
                {lead.message && (
                  <p className="mt-2 text-base text-slate-600 bg-slate-50 rounded-lg px-3 py-2">{lead.message}</p>
                )}
                <p className="mt-2 text-sm text-slate-400">{new Date(lead.created_at).toLocaleString()}</p>
              </div>
              <div className="relative flex items-center gap-2">
                <span className={clsx('text-sm px-2 py-1 rounded-full font-medium', STATUS_COLORS[lead.status] || STATUS_COLORS.new)}>
                  {lead.status}
                </span>
                <button
                  onClick={() => setMenuOpen(menuOpen === lead.id ? null : lead.id)}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"
                  aria-label="Change lead status"
                >
                  <MoreVertical size={18} />
                </button>
                {menuOpen === lead.id && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(null)} />
                    <div className="absolute right-0 top-full mt-1 w-36 rounded-xl border border-slate-200 bg-white shadow-md z-20 py-1">
                      {STATUSES.map((s) => (
                        <button
                          key={s}
                          onClick={() => { updateMut.mutate({ id: lead.id, status: s }); setMenuOpen(null) }}
                          className={clsx(
                            'w-full text-left px-3 py-1.5 text-sm capitalize hover:bg-slate-50',
                            s === lead.status ? 'font-semibold text-brand-600' : 'text-slate-600'
                          )}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </Card>
        ))}
        {leads.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">No leads yet. They'll appear here when visitors contact you.</div>
        )}
      </div>
    </div>
  )
}
