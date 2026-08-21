import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Clock } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { usePlan } from '../../shared/hooks/usePlan'
import { MessageSquare, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'

interface Message {
  id: string
  sender: string
  content: string
  created_at: string
}

interface Conversation {
  id: string
  session_id: string
  status: string
  started_at: string
  messages: Message[]
}

export function ConversationsPage() {
  const qc = useQueryClient()
  const { data: conversations = [] } = useQuery<Conversation[]>({
    queryKey: ['conversations'],
    queryFn: () => api.get('/chat/conversations').then((r) => r.data),
  })
  const [open, setOpen] = useState<string | null>(null)
  const { data: plan } = usePlan()
  const historyDays = plan?.limits.conversation_history_days ?? null

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/chat/conversations/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      // Deleting a conversation changes message/lead counts and top-question
      // rankings on the Overview page -- without this it shows stale data
      // until a manual refresh.
      qc.invalidateQueries({ queryKey: ['analytics'] })
    },
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Conversations</h1>
        <p className="text-base text-slate-500 mt-1">All chat sessions with your website visitors.</p>
      </div>

      {historyDays !== null && (
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-base text-slate-500">
          <Clock size={16} className="flex-shrink-0" />
          <span className="flex-1">
            Showing conversations from the last {historyDays} days — that's your plan's history limit. Older
            conversations aren't deleted, just hidden until you upgrade.
          </span>
          <Link to="/dashboard/plan" className="font-semibold text-brand-600 underline flex-shrink-0">
            Upgrade
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {conversations.map((conv) => (
          <Card key={conv.id}>
            <button
              onClick={() => setOpen(open === conv.id ? null : conv.id)}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-3">
                <MessageSquare size={18} className="text-brand-500" />
                <div>
                  <p className="text-lg font-medium text-slate-900">Session {conv.session_id.slice(0, 8)}…</p>
                  <p className="text-sm text-slate-400">{new Date(conv.started_at).toLocaleString()}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx('text-sm px-2 py-0.5 rounded-full', conv.status === 'open' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500')}>
                  {conv.status}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    if (confirm('Delete this conversation? This cannot be undone.')) {
                      deleteMut.mutate(conv.id)
                    }
                  }}
                  className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                  aria-label="Delete conversation"
                >
                  <Trash2 size={14} />
                </button>
                {open === conv.id ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
              </div>
            </button>

            {open === conv.id && conv.messages.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
                {conv.messages.map((msg) => (
                  <div key={msg.id} className={clsx('flex', msg.sender === 'visitor' ? 'justify-start' : 'justify-end')}>
                    <div className={clsx('max-w-xs px-3 py-2 rounded-2xl text-base', msg.sender === 'visitor' ? 'bg-slate-100 text-slate-800' : 'bg-brand-500 text-white')}>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
        {conversations.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">No conversations yet.</div>
        )}
      </div>
    </div>
  )
}
