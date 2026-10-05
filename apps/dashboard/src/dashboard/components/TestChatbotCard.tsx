import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Send, RotateCcw } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { MarkdownText } from '../../widget/MarkdownText'
import { t as translateNow, useT } from '../../shared/i18n'

interface Turn {
  sender: 'you' | 'bot'
  text: string
  /** Low confidence = the knowledge base didn't really cover the question. */
  weak?: boolean
}

const newSession = () => `test_${Math.random().toString(36).slice(2, 10)}`

/**
 * QA 2026-10-02 (E5): owners could only check answers through the live widget, which also
 * counted toward their plan and showed up in Conversations and the stats. This uses the same
 * answer pipeline (POST /api/chat/test) but is marked as a test, so none of that happens.
 */
export function TestChatbotCard() {
  const { t } = useT()
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const session = useRef(newSession())
  const bottom = useRef<HTMLDivElement>(null)

  const askMut = useMutation({
    mutationFn: (message: string) =>
      api.post('/chat/test', { session_id: session.current, message }).then((r) => r.data as { reply: string; confidence: number | null }),
    onSuccess: (data) => {
      setTurns((t) => [...t, { sender: 'bot', text: data.reply, weak: (data.confidence ?? 1) < 0.3 }])
      setTimeout(() => bottom.current?.scrollIntoView({ block: 'nearest' }), 0)
    },
    onError: () => setTurns((prev) => [...prev, { sender: 'bot', text: translateNow('testChat.failed'), weak: true }]),
  })

  const send = () => {
    const message = input.trim()
    if (!message || askMut.isPending) return
    setTurns((t) => [...t, { sender: 'you', text: message }])
    setInput('')
    askMut.mutate(message)
  }

  const reset = () => {
    session.current = newSession()
    setTurns([])
  }

  return (
    <Card title={t('testChat.title')}>
      <p className="mb-3 text-sm text-slate-500">{t('testChat.intro')}</p>
      <div className="max-h-80 space-y-2 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3" aria-live="polite">
        {turns.length === 0 && <p className="text-sm text-slate-400">{t('testChat.examples')}</p>}
        {turns.map((turn, i) => (
          <div key={i} className={clsx('flex', turn.sender === 'you' ? 'justify-end' : 'justify-start')}>
            <div
              className={clsx(
                'max-w-[85%] rounded-2xl px-3 py-2 text-sm',
                turn.sender === 'you' ? 'bg-brand-500 text-white' : 'bg-white text-slate-800 border border-slate-200'
              )}
            >
              {turn.sender === 'bot' ? <MarkdownText text={turn.text} /> : turn.text}
              {turn.weak && turn.sender === 'bot' && (
                <p className="mt-1 text-xs text-amber-700">{t('testChat.weak')}</p>
              )}
            </div>
          </div>
        ))}
        {askMut.isPending && <p className="text-sm text-slate-400">{t('testChat.thinking')}</p>}
        <div ref={bottom} />
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          maxLength={2000}
          placeholder={t('testChat.placeholder')}
          aria-label={t('testChat.inputLabel')}
          className="flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-400"
        />
        <button
          onClick={send}
          disabled={!input.trim() || askMut.isPending}
          className="brand-gradient flex h-10 w-10 items-center justify-center rounded-full text-white disabled:opacity-40"
          aria-label={t('testChat.send')}
        >
          <Send size={15} />
        </button>
        <button onClick={reset} className="flex h-10 w-10 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100" aria-label={t('testChat.reset')} title={t('testChat.reset')}>
          <RotateCcw size={15} />
        </button>
      </div>
    </Card>
  )
}
