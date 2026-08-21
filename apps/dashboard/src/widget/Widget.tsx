import { useState, useEffect } from 'react'
import { MessageCircle, X } from 'lucide-react'
import { ChatWindow } from './ChatWindow'
import { widgetStrings } from './i18n'

interface Props {
  businessId: string
  primaryColor?: string
  welcomeMessage?: string
  botName?: string
  apiBaseUrl?: string
}

const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const DEFAULT_WELCOME_MESSAGE = 'Hi! How can I help you today?'

export function Widget({
  businessId,
  primaryColor = '#ff6b00',
  welcomeMessage,
  botName = 'Support Chat',
  apiBaseUrl = DEFAULT_API_BASE_URL,
}: Props) {
  const [open, setOpen] = useState(false)
  const [fetchedWelcomeMessage, setFetchedWelcomeMessage] = useState<string | null>(null)
  const [fetchedPrimaryColor, setFetchedPrimaryColor] = useState<string | null>(null)
  // The business's first configured language -- not the visitor's browser locale,
  // which has no relationship to what a visitor is about to type. Once the visitor
  // sends a message, ChatWindow takes over and tracks the conversation's actual
  // detected language itself (see its `lang` state, driven by each reply).
  const [primaryLang, setPrimaryLang] = useState<string>('en')

  useEffect(() => {
    let cancelled = false
    fetch(`${apiBaseUrl}/api/businesses/${businessId}/public-settings`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled) return
        const languages: string[] = data?.languages ?? []
        setPrimaryLang(languages[0] ?? 'en')
        if (data?.welcome_message) setFetchedWelcomeMessage(data.welcome_message)
        if (data?.primary_color) setFetchedPrimaryColor(data.primary_color)
      })
      .catch(() => {
        // Silently keep the default/prop values if this fails — never block
        // the widget from opening over a settings fetch error.
      })
    return () => {
      cancelled = true
    }
  }, [apiBaseUrl, businessId])

  const resolvedWelcomeMessage = fetchedWelcomeMessage ?? welcomeMessage ?? DEFAULT_WELCOME_MESSAGE
  const strings = widgetStrings(primaryLang)
  // The dashboard-saved color (fetched above) wins over the script tag's data-color, so
  // picking a color in Settings applies to the live widget with no embed-code edits. The
  // data-color attribute still works as a manual override if the fetch fails or is skipped.
  const resolvedPrimaryColor = fetchedPrimaryColor ?? primaryColor

  return (
    <div className="fixed bottom-5 right-5 z-[9999] flex flex-col items-end gap-3">
      {open && (
        <div className="w-[360px] h-[520px] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-gray-200 animate-in slide-in-from-bottom-4">
          <div className="px-4 py-3 flex items-center justify-between flex-shrink-0" style={{ backgroundColor: resolvedPrimaryColor }}>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-400 rounded-full" />
              <span className="text-white text-sm font-medium">{botName}</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white">
              <X size={18} />
            </button>
          </div>
          <ChatWindow businessId={businessId} primaryColor={resolvedPrimaryColor} welcomeMessage={resolvedWelcomeMessage} apiBaseUrl={apiBaseUrl} initialLang={primaryLang} />
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        className="w-14 h-14 rounded-full shadow-lg flex items-center justify-center text-white hover:scale-105 transition-transform"
        style={{ backgroundColor: resolvedPrimaryColor }}
        aria-label={open ? strings.closeChat : strings.openChat}
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>
    </div>
  )
}
