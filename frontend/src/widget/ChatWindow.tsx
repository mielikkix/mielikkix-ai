import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import { LeadForm } from './LeadForm'
import { MarkdownText } from './MarkdownText'
import { widgetStrings } from './i18n'

interface Message {
  sender: 'visitor' | 'ai'
  content: string
}

interface Props {
  businessId: string
  welcomeMessage?: string
  primaryColor?: string
  apiBaseUrl?: string
  // Starting point only (the business's primary language) -- once the visitor
  // sends a message, `lang` below tracks whatever language the backend actually
  // detected from that message, so the lead form and other chrome stay in sync
  // with the conversation instead of a fixed guess made before anyone typed.
  initialLang?: string
}

const genSession = () => `sess_${Math.random().toString(36).slice(2, 10)}`
const SESSION_KEY = 'mielikkix_session'
const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export function ChatWindow({
  businessId,
  welcomeMessage = 'Hi! How can I help you today?',
  primaryColor = '#ff6b00',
  apiBaseUrl = DEFAULT_API_BASE_URL,
  initialLang,
}: Props) {
  const [lang, setLang] = useState(initialLang ?? 'en')
  const strings = widgetStrings(lang)
  const sessionId = useRef(sessionStorage.getItem(SESSION_KEY) || (() => {
    const s = genSession(); sessionStorage.setItem(SESSION_KEY, s); return s
  })())

  const [messages, setMessages] = useState<Message[]>([{ sender: 'ai', content: welcomeMessage }])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showLeadForm, setShowLeadForm] = useState(false)
  const [inputFocused, setInputFocused] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages((m) => [...m, { sender: 'visitor', content: msg }])
    setLoading(true)
    try {
      const res = await fetch(`${apiBaseUrl}/api/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ business_id: businessId, session_id: sessionId.current, message: msg }),
      })
      if (res.status === 429) {
        setMessages((m) => [...m, { sender: 'ai', content: strings.rateLimited }])
        return
      }
      if (!res.ok) throw new Error('Request failed')
      const data = await res.json()
      if (data.lang) setLang(data.lang)
      setMessages((m) => [...m, { sender: 'ai', content: data.reply }])
      if (data.suggest_lead_capture) setShowLeadForm(true)
    } catch {
      setMessages((m) => [...m, { sender: 'ai', content: strings.chatError }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.sender === 'visitor' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm leading-relaxed ${
                msg.sender === 'visitor'
                  ? 'text-white rounded-br-sm'
                  : 'bg-gray-100 text-gray-800 rounded-bl-sm'
              }`}
              style={msg.sender === 'visitor' ? { backgroundColor: primaryColor } : undefined}
            >
              {msg.sender === 'ai' ? <MarkdownText text={msg.content} /> : msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-3 py-2 rounded-2xl rounded-bl-sm">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.1}s` }} />
                ))}
              </span>
            </div>
          </div>
        )}
        {showLeadForm && (
          <div className="bg-white border border-gray-200 rounded-xl p-3">
            <p className="text-sm font-medium text-gray-800 mb-2">{strings.leadFormIntro}</p>
            <LeadForm
              businessId={businessId}
              sessionId={sessionId.current}
              primaryColor={primaryColor}
              apiBaseUrl={apiBaseUrl}
              lang={lang}
              onSubmitted={() => {
                setShowLeadForm(false)
                setMessages((m) => [...m, { sender: 'ai', content: strings.leadThanks }])
              }}
            />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-gray-100 px-3 py-3 flex gap-2">
        <input
          className="flex-1 rounded-full border px-4 py-2 text-sm outline-none"
          style={{ borderColor: inputFocused ? primaryColor : '#d1d5db' }}
          placeholder={strings.inputPlaceholder}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
        />
        <button
          onClick={send}
          disabled={!input.trim() || loading}
          className="w-9 h-9 flex items-center justify-center rounded-full text-white disabled:opacity-40 flex-shrink-0"
          style={{ backgroundColor: primaryColor }}
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  )
}
