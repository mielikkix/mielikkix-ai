import { useEffect, useState } from 'react'
import { widgetStrings } from './i18n'

interface Slot {
  start: string
  end: string
}

interface Props {
  primaryColor?: string
  apiBaseUrl?: string
  lang?: string
  // The visitor's own chat message that triggered this flow (see
  // chat_service.py's suggest_booking_flow) -- seeds the describe step and
  // fires the first availability search automatically, so the visitor
  // doesn't have to retype what they just said.
  initialMessage: string
  // Called with a human-readable confirmation line right after a
  // successful booking -- the caller (ChatWindow) posts it as a normal
  // chat message and unmounts this component immediately after, same
  // "hide the form, add a thank-you bubble" pattern LeadForm's onSubmitted
  // uses. BookingFlow's own "done" step below is otherwise unreachable
  // (the parent removes this component the instant onBooked fires), so the
  // confirmation text has to travel up rather than render locally.
  onBooked: (confirmationText: string) => void
}

const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const DEFAULT_PRIMARY_COLOR = '#ff6b00'

type Step = 'describe' | 'slots' | 'details'

// The browser already knows the visitor's real timezone precisely -- sent
// straight to the server rather than asked of the LLM (see
// agents_booking.py's _RequestBookingBody comment on why parsing a
// timezone out of free text is a bad idea).
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone

function formatSlot(startISO: string): string {
  return new Date(startISO).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function BookingFlow({
  primaryColor = DEFAULT_PRIMARY_COLOR,
  apiBaseUrl = DEFAULT_API_BASE_URL,
  lang,
  initialMessage,
  onBooked,
}: Props) {
  const strings = widgetStrings(lang)

  const [step, setStep] = useState<Step>('describe')
  const [message, setMessage] = useState(initialMessage)
  const [meetingType, setMeetingType] = useState('appointment')
  const [slots, setSlots] = useState<Slot[]>([])
  const [chosenSlot, setChosenSlot] = useState<Slot | null>(null)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const findTimes = async (text: string) => {
    if (!text.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${apiBaseUrl}/api/agents/booking/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, timezone }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'request failed')

      setMeetingType(data.meeting_type || 'appointment')
      if (data.status === 'clarification_needed') {
        setError(data.clarification_question || strings.bookingGenericError)
        return
      }
      if (data.status === 'no_availability') {
        setError(strings.bookingNoAvailability)
        return
      }
      setSlots(data.slots || [])
      setStep('slots')
    } catch {
      setError(strings.bookingGenericError)
    } finally {
      setLoading(false)
    }
  }

  // Fires once, using the chat message that triggered this component in
  // the first place -- see this component's own Props doc on why.
  useEffect(() => {
    findTimes(initialMessage)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const pickSlot = (slot: Slot) => {
    setChosenSlot(slot)
    setError('')
    setStep('details')
  }

  const confirm = async () => {
    if (!name || !email || !chosenSlot) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${apiBaseUrl}/api/agents/booking/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          email,
          start: chosenSlot.start,
          end: chosenSlot.end,
          timezone,
          meeting_type: meetingType,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'confirm failed')

      if (data.status === 'conflict') {
        setError(strings.bookingConflict)
        setStep('slots')
        return
      }
      onBooked(`${strings.bookingBooked} ${formatSlot(chosenSlot.start)}`)
    } catch {
      setError(strings.bookingGenericError)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 space-y-2">
      {step === 'describe' && (
        <>
          <input
            className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button
            onClick={() => findTimes(message)}
            disabled={loading || !message.trim()}
            className="w-full text-white text-sm py-1.5 rounded-lg transition-[filter] hover:brightness-90 disabled:opacity-50"
            style={{ backgroundColor: primaryColor }}
          >
            {loading ? strings.bookingFinding : strings.bookingFindTimes}
          </button>
        </>
      )}

      {step === 'slots' && (
        <>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {slots.map((slot) => (
              <button
                key={slot.start}
                onClick={() => pickSlot(slot)}
                className="w-full text-left rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm hover:border-gray-400"
              >
                {formatSlot(slot.start)}
              </button>
            ))}
          </div>
          <button
            onClick={() => setStep('describe')}
            className="text-xs font-medium"
            style={{ color: primaryColor }}
          >
            {strings.bookingBackToDescribe}
          </button>
        </>
      )}

      {step === 'details' && chosenSlot && (
        <>
          <p className="text-sm font-medium text-gray-800">{formatSlot(chosenSlot.start)}</p>
          <input
            className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm"
            placeholder={strings.bookingNamePlaceholder}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm"
            placeholder={strings.bookingEmailPlaceholder}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button
            onClick={confirm}
            disabled={loading || !name || !email}
            className="w-full text-white text-sm py-1.5 rounded-lg transition-[filter] hover:brightness-90 disabled:opacity-50"
            style={{ backgroundColor: primaryColor }}
          >
            {loading ? strings.bookingConfirming : strings.bookingConfirm}
          </button>
          <button
            onClick={() => setStep('slots')}
            className="text-xs font-medium"
            style={{ color: primaryColor }}
          >
            {strings.bookingBackToSlots}
          </button>
        </>
      )}
    </div>
  )
}
