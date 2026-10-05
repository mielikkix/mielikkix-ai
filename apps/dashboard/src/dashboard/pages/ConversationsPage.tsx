import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Clock, Search, MessageSquare, ChevronDown, ChevronUp, Trash2, CheckCircle2, RotateCcw } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { usePlan } from '../../shared/hooks/usePlan'
import { clsx } from 'clsx'
import { useT, type MessageKey } from '../../shared/i18n'

interface Message {
  id: string
  sender: string
  content: string
  created_at: string
}

interface Conversation {
  id: string
  session_id: string
  status: 'open' | 'closed' | string
  started_at: string
  messages: Message[]
  language: string | null
  preview: string | null
  last_message_at: string | null
}

// An open conversation with no message for a day is shown as "Idle" -- QA 2026-10-02 (D10)
// saw all 37 conversations as "open" forever. Owners can close it; the visitor writing again reopens it.
const IDLE_AFTER_MS = 24 * 60 * 60 * 1000

function statusLabel(conv: Conversation): { key: MessageKey; className: string } {
  if (conv.status === 'closed') return { key: 'conversations.status.closed', className: 'bg-slate-100 text-slate-500' }
  const last = conv.last_message_at ? new Date(conv.last_message_at).getTime() : 0
  if (last && Date.now() - last > IDLE_AFTER_MS) return { key: 'conversations.status.idle', className: 'bg-amber-50 text-amber-700' }
  return { key: 'conversations.status.open', className: 'bg-green-100 text-green-700' }
}

export function ConversationsPage() {
  const qc = useQueryClient()
  const { t, formatDateTime, formatTime, languageName } = useT()
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [statusFilter, setStatusFilter] = useState<'' | 'open' | 'closed'>('')
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])

  const { data: conversations = [], isFetching } = useQuery<Conversation[]>({
    queryKey: ['conversations', debounced, statusFilter],
    queryFn: () =>
      api
        .get('/chat/conversations', { params: { q: debounced || undefined, status: statusFilter || undefined } })
        .then((r) => r.data),
  })
  const [open, setOpen] = useState<string | null>(null)
  const { data: plan } = usePlan()
  const historyDays = plan?.limits.conversation_history_days ?? null

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['conversations'] })
    // Deleting a conversation changes message/lead counts and top-question
    // rankings on the Overview page -- without this it shows stale data
    // until a manual refresh.
    qc.invalidateQueries({ queryKey: ['analytics'] })
  }

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/chat/conversations/${id}`),
    onSuccess: invalidate,
  })

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'open' | 'closed' }) => api.patch(`/chat/conversations/${id}`, { status }),
    onSuccess: invalidate,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">{t('conversations.title')}</h1>
        <p className="text-base text-slate-500 mt-1">{t('conversations.subtitle')}</p>
      </div>

      {historyDays !== null && (
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-base text-slate-500">
          <Clock size={16} className="flex-shrink-0" />
          <span className="flex-1">{t('conversations.historyLimit', { days: historyDays })}</span>
          <Link to="/dashboard/plan" className="font-semibold text-brand-600 underline flex-shrink-0">
            {t('conversations.upgrade')}
          </Link>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[14rem]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('conversations.searchPlaceholder')}
            aria-label={t('conversations.searchLabel')}
            className="w-full rounded-xl border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-400"
          />
        </div>
        <div className="flex gap-1.5" role="group" aria-label={t('conversations.filterLabel')}>
          {([['', 'conversations.filters.all'], ['open', 'conversations.filters.open'], ['closed', 'conversations.filters.closed']] as const).map(([value, label]) => (
            <button
              key={label}
              onClick={() => setStatusFilter(value)}
              aria-pressed={statusFilter === value}
              className={clsx(
                'rounded-full border px-3 py-1 text-sm font-medium',
                statusFilter === value ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
              )}
            >
              {t(label)}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {conversations.map((conv) => {
          const status = statusLabel(conv)
          const visitorMessages = conv.messages.filter((m) => m.sender === 'visitor').length
          return (
            <Card key={conv.id}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => setOpen(open === conv.id ? null : conv.id)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setOpen(open === conv.id ? null : conv.id)}
                className="w-full flex items-start justify-between gap-3 text-left cursor-pointer"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <MessageSquare size={18} className="mt-1 flex-shrink-0 text-brand-500" />
                  <div className="min-w-0">
                    <p className="truncate text-base font-medium text-slate-900">{conv.preview ?? t('conversations.session', { id: conv.session_id.slice(0, 8) })}</p>
                    <p className="text-sm text-slate-400">
                      {formatDateTime(conv.started_at)}
                      {' · '}
                      {t('conversations.messages', { count: visitorMessages })}
                      {conv.language && ` · ${languageName(conv.language)}`}
                    </p>
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-2">
                  <span className={clsx('text-sm px-2 py-0.5 rounded-full', status.className)}>{t(status.key)}</span>
                  {conv.status === 'closed' ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); statusMut.mutate({ id: conv.id, status: 'open' }) }}
                      className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-slate-500 hover:bg-slate-100"
                      title={t('conversations.reopen')}
                    >
                      <RotateCcw size={13} /> {t('conversations.reopen')}
                    </button>
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); statusMut.mutate({ id: conv.id, status: 'closed' }) }}
                      className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-slate-500 hover:bg-slate-100"
                      title={t('conversations.markDone')}
                    >
                      <CheckCircle2 size={13} /> {t('conversations.close')}
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (confirm(t('conversations.deleteConfirm'))) {
                        deleteMut.mutate(conv.id)
                      }
                    }}
                    className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                    aria-label={t('conversations.delete')}
                  >
                    <Trash2 size={14} />
                  </button>
                  {open === conv.id ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
                </div>
              </div>

              {open === conv.id && conv.messages.length > 0 && (
                <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
                  {conv.messages.map((msg) => (
                    <div key={msg.id} className={clsx('flex', msg.sender === 'visitor' ? 'justify-start' : 'justify-end')}>
                      <div className={clsx('max-w-md px-3 py-2 rounded-2xl text-base whitespace-pre-line', msg.sender === 'visitor' ? 'bg-slate-100 text-slate-800' : 'bg-brand-500 text-white')}>
                        {msg.content}
                        <span className={clsx('mt-1 block text-[11px]', msg.sender === 'visitor' ? 'text-slate-400' : 'text-brand-100')}>
                          {formatTime(msg.created_at)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )
        })}
        {conversations.length === 0 && !isFetching && (
          <div className="text-center py-12 text-slate-400 text-base">
            {debounced || statusFilter ? t('conversations.noMatch') : t('conversations.empty')}
          </div>
        )}
      </div>
    </div>
  )
}
