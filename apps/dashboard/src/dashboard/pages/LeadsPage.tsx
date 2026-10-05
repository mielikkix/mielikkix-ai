import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { clsx } from 'clsx'
import { Download, Search, Trash2 } from 'lucide-react'
import { t as translateNow, useT, type MessageKey } from '../../shared/i18n'

interface Lead {
  id: string
  name: string
  email: string | null
  phone: string | null
  message: string | null
  status: string
  notes: string | null
  created_at: string
  updated_at: string | null
  company?: string | null
  interest?: string | null
  source?: string | null
}

// The pipeline, in order. DEMO_REQUESTED is the first stage of a demo request from
// mielikkix.ai (lead_service); the API rejects anything not in this list.
// QA 2026-10-02 (D4/M6): statuses showed as raw values (DEMO_REQUESTED, new, won) and
// the only control was hidden behind an unlabelled "..." menu.
// The stored status values never change with the language; only their labels do.
const STATUSES: { value: string; label: MessageKey; color: string }[] = [
  { value: 'new', label: 'leads.statuses.new', color: 'bg-blue-100 text-blue-700' },
  { value: 'DEMO_REQUESTED', label: 'leads.statuses.DEMO_REQUESTED', color: 'bg-violet-100 text-violet-700' },
  { value: 'contacted', label: 'leads.statuses.contacted', color: 'bg-yellow-100 text-yellow-700' },
  { value: 'won', label: 'leads.statuses.won', color: 'bg-green-100 text-green-700' },
  { value: 'lost', label: 'leads.statuses.lost', color: 'bg-slate-100 text-slate-500' },
]
const statusInfo = (value: string) => {
  const known = STATUSES.find((s) => s.value === value)
  return known
    ? { value, label: translateNow(known.label), color: known.color }
    : { value, label: value, color: 'bg-slate-100 text-slate-600' }
}

function csvCell(value: unknown): string {
  const text = value == null ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadCsv(leads: Lead[]) {
  // Column headers and status labels follow the UI language; the lead data is exported as entered.
  const header = (['name', 'email', 'phone', 'company', 'status', 'interest', 'source', 'message', 'notes', 'created', 'updated'] as const).map(
    (k) => translateNow(`leads.csv.${k}`),
  )
  const rows = leads.map((l) => [
    l.name, l.email, l.phone, l.company, statusInfo(l.status).label, l.interest, l.source, l.message, l.notes,
    l.created_at, l.updated_at,
  ])
  // BOM so Excel opens Norwegian characters (æ, ø, å) correctly.
  const csv = '﻿' + [header, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `leads-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function LeadNotes({ lead }: { lead: Lead }) {
  const qc = useQueryClient()
  const { t } = useT()
  const [value, setValue] = useState(lead.notes ?? '')
  const saveMut = useMutation({
    mutationFn: (notes: string) => api.patch(`/leads/${lead.id}`, { notes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })
  const dirty = value.trim() !== (lead.notes ?? '')
  return (
    <div className="mt-3">
      <label htmlFor={`notes-${lead.id}`} className="text-xs font-medium text-slate-500">
        {t('leads.notes')}
      </label>
      <textarea
        id={`notes-${lead.id}`}
        rows={2}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => dirty && saveMut.mutate(value)}
        placeholder={t('leads.notesPlaceholder')}
        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-400"
      />
      {saveMut.isPending && <p className="text-xs text-slate-400">{t('leads.notesSaving')}</p>}
      {saveMut.isError && <p role="alert" className="text-xs text-red-600">{t('leads.notesFailed')}</p>}
    </div>
  )
}

export function LeadsPage() {
  const qc = useQueryClient()
  // useT() also re-renders this page on a language change, which re-labels statusInfo()'s badges.
  const { t, formatDateTime } = useT()
  const { data: leads = [] } = useQuery<Lead[]>({
    queryKey: ['leads'],
    queryFn: () => api.get('/leads').then((r) => r.data),
  })
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patch(`/leads/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })

  // GDPR Phase 5: a visitor asked this business to delete their data. Removes
  // this lead, their other leads (same email/phone) and their conversations.
  const eraseMut = useMutation({
    mutationFn: (id: string) => api.post('/chat/visitors/erase', { lead_id: id }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] })
      qc.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const l of leads) c[l.status] = (c[l.status] ?? 0) + 1
    return c
  }, [leads])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return leads.filter((l) => {
      if (statusFilter && l.status !== statusFilter) return false
      if (!q) return true
      return [l.name, l.email, l.phone, l.company, l.message, l.notes].some((f) => f?.toLowerCase().includes(q))
    })
  }, [leads, query, statusFilter])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">{t('leads.title')}</h1>
          <p className="text-base text-slate-500 mt-1">{t('leads.subtitle')}</p>
        </div>
        <Button size="sm" variant="secondary" disabled={visible.length === 0} onClick={() => downloadCsv(visible)}>
          <Download size={16} className="mr-1" /> {t('leads.exportCsv')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[14rem]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('leads.searchPlaceholder')}
            aria-label={t('leads.searchLabel')}
            className="w-full rounded-xl border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-400"
          />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('leads.filterLabel')}>
          {[{ value: '', label: 'leads.all' as MessageKey }, ...STATUSES].map((s) => {
            const n = s.value ? counts[s.value] ?? 0 : leads.length
            if (s.value && n === 0) return null
            return (
              <button
                key={s.value || 'all'}
                onClick={() => setStatusFilter(s.value)}
                aria-pressed={statusFilter === s.value}
                className={clsx(
                  'rounded-full border px-3 py-1 text-sm font-medium',
                  statusFilter === s.value ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                )}
              >
                {t(s.label)} <span className="text-slate-400">{n}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="space-y-3">
        {visible.map((lead) => {
          const info = statusInfo(lead.status)
          return (
            <Card key={lead.id}>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-slate-900">{lead.name}</p>
                    {lead.company && <span className="text-sm text-slate-500">· {lead.company}</span>}
                    <span className={clsx('rounded-full px-2 py-0.5 text-xs font-medium', info.color)}>{info.label}</span>
                  </div>
                  <div className="flex gap-3 mt-1 text-sm text-slate-500 flex-wrap">
                    {lead.email && <a href={`mailto:${lead.email}`} className="hover:text-brand-600">{lead.email}</a>}
                    {lead.phone && <a href={`tel:${lead.phone}`} className="hover:text-brand-600">{lead.phone}</a>}
                    {lead.interest && <span>{t('leads.interestedIn', { interest: lead.interest })}</span>}
                  </div>
                  {lead.message && (
                    <p className="mt-2 text-base text-slate-600 bg-slate-50 rounded-lg px-3 py-2 whitespace-pre-line">{lead.message}</p>
                  )}
                  <LeadNotes lead={lead} />
                  <p className="mt-2 text-sm text-slate-400">
                    {t('leads.created', { date: formatDateTime(lead.created_at) })}
                    {lead.updated_at && <> · {t('leads.updated', { date: formatDateTime(lead.updated_at) })}</>}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <label className="flex items-center gap-2 text-sm text-slate-600">
                    {t('leads.status')}
                    <select
                      value={lead.status}
                      onChange={(e) => updateMut.mutate({ id: lead.id, status: e.target.value })}
                      className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                    >
                      {STATUSES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {t(s.label)}
                        </option>
                      ))}
                      {!STATUSES.some((s) => s.value === lead.status) && <option value={lead.status}>{lead.status}</option>}
                    </select>
                  </label>
                  <button
                    onClick={() => {
                      if (confirm(t('leads.eraseConfirm', { name: lead.name }))) {
                        eraseMut.mutate(lead.id)
                      }
                    }}
                    className="flex items-center gap-1 text-xs text-slate-400 hover:text-red-600"
                  >
                    <Trash2 size={12} /> {t('leads.erase')}
                  </button>
                </div>
              </div>
            </Card>
          )
        })}
        {leads.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">{t('leads.empty')}</div>
        )}
        {leads.length > 0 && visible.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">{t('leads.noMatch')}</div>
        )}
      </div>
    </div>
  )
}
