import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { usePlan } from '../../shared/hooks/usePlan'
import { SettingsNav, SettingsTab, isSettingsTab } from '../components/SettingsNav'
import { PersonalitySection } from './settings/PersonalitySection'
import { AppearanceSection } from './settings/AppearanceSection'
import { LanguagesSection } from './settings/LanguagesSection'
import { BookingSection } from './settings/BookingSection'
import { AdvancedSection } from './settings/AdvancedSection'
import {
  AVAILABLE_LANGUAGES,
  Business,
  BusinessHours,
  CalendarStatus,
  DayHours,
  HEX_COLOR_REGEX,
  Settings,
} from './settings/types'

// This page owns every query/mutation/piece of form state; the five
// section components below (settings/*Section.tsx) are presentational
// only. That split is deliberate, not incidental: switching the active
// section (via ?tab= below) must never re-fetch or re-initialize a
// section's own slice of state, or an unsaved edit in one section could
// silently vanish when the visitor switches away and back before saving.
export function SettingsPage() {
  const qc = useQueryClient()
  const { data } = useQuery<Settings>({
    queryKey: ['settings'],
    queryFn: () => api.get('/businesses/me/settings').then((r) => r.data),
  })

  const [form, setForm] = useState<Partial<Settings>>({})
  useEffect(() => { if (data) setForm(data) }, [data])

  const set = (k: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  // Each section saves only the fields it owns (matching the
  // languages/business-hours mutations further below, which already did
  // this) -- replaces the old single catch-all mutation that resubmitted
  // the entire form regardless of which card's button was clicked.
  const personalityMut = useMutation({
    mutationFn: () =>
      api.patch('/businesses/me/settings', {
        tone: form.tone,
        welcome_message: form.welcome_message,
        fallback_message: form.fallback_message,
        fallback_messages: form.fallback_messages,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  const advancedMut = useMutation({
    mutationFn: () =>
      api.patch('/businesses/me/settings', {
        contact_email: form.contact_email,
        contact_phone: form.contact_phone,
        llm_provider: form.llm_provider,
        llm_model: form.llm_model,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  // Widget color lives on the Business resource (not BusinessSettings above), so it gets
  // its own query/mutation and its own save action.
  const { data: business } = useQuery<Business>({
    queryKey: ['business'],
    queryFn: () => api.get('/businesses/me').then((r) => r.data),
  })

  const [color, setColor] = useState('#ff6b00')
  useEffect(() => { if (business?.primary_color) setColor(business.primary_color) }, [business])
  const isValidColor = HEX_COLOR_REGEX.test(color)

  const colorMut = useMutation({
    mutationFn: (primary_color: string) => api.patch('/businesses/me', { primary_color }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['business'] }),
  })

  const { data: plan } = usePlan()
  const customBrandingAllowed = !!plan?.features.custom_branding
  const maxLanguages = plan?.limits.max_languages ?? 1

  const languages = form.languages ?? ['en']
  const fallbackMessages = form.fallback_messages ?? {}
  const setFallbackMessageFor = (code: string) => (e: React.ChangeEvent<HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, fallback_messages: { ...(f.fallback_messages ?? {}), [code]: e.target.value } }))
  const languageLabel = (code: string) => AVAILABLE_LANGUAGES.find((l) => l.code === code)?.label ?? code
  const toggleLanguage = (code: string) => {
    const has = languages.includes(code)
    if (has) {
      setForm((f) => ({ ...f, languages: languages.filter((l) => l !== code) }))
    } else if (languages.length < maxLanguages) {
      setForm((f) => ({ ...f, languages: [...languages, code] }))
    }
  }

  const languagesMut = useMutation({
    mutationFn: (langs: string[]) => api.patch('/businesses/me/settings', { languages: langs }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  const businessHours = form.business_hours ?? {}
  const setDayHours = (day: keyof BusinessHours, hours: DayHours | null) =>
    setForm((f) => ({ ...f, business_hours: { ...(f.business_hours ?? {}), [day]: hours } }))

  const businessHoursMut = useMutation({
    mutationFn: (hours: BusinessHours) => api.patch('/businesses/me/settings', { business_hours: hours }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  // Booking Assistant's per-tenant Google Calendar connection (see
  // app/api/calendar_oauth.py) -- only queried once the plan actually
  // includes it, same "don't fetch what you can't use" reasoning as the
  // api-access-addon card elsewhere in this app.
  const bookingEnabled = !!plan?.features.booking_enabled

  const { data: calendarStatus } = useQuery<CalendarStatus>({
    queryKey: ['calendar-status'],
    queryFn: () => api.get('/businesses/me/calendar/status').then((r) => r.data),
    enabled: bookingEnabled,
  })

  const disconnectCalendarMut = useMutation({
    mutationFn: () => api.delete('/businesses/me/calendar'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['calendar-status'] }),
  })

  // The OAuth flow redirects the browser back here with ?calendar=connected
  // or ?calendar=error (see calendar_oauth.py's callback()) -- captured
  // into local state and stripped from the URL immediately, so a page
  // refresh doesn't keep re-showing a banner from a connection attempt
  // that already happened. Same searchParams instance also drives the
  // section switcher below (?tab=) -- both params coexist fine in one
  // URLSearchParams.
  const [searchParams, setSearchParams] = useSearchParams()
  const [calendarBanner, setCalendarBanner] = useState<'connected' | 'error' | null>(null)
  useEffect(() => {
    const value = searchParams.get('calendar')
    if (value === 'connected' || value === 'error') {
      setCalendarBanner(value)
      qc.invalidateQueries({ queryKey: ['calendar-status'] })
      const next = new URLSearchParams(searchParams)
      next.delete('calendar')
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Active section: ?tab= in the URL, defaulting to 'personality' -- except
  // right after an OAuth redirect (?calendar= present, ?tab= absent/stale),
  // where it defaults to 'booking' instead so the connect/error banner
  // above actually lands somewhere visible, rather than on whichever
  // section happens to be first.
  const rawTab = searchParams.get('tab')
  const tab: SettingsTab = isSettingsTab(rawTab) ? rawTab : searchParams.has('calendar') ? 'booking' : 'personality'
  const setTab = (next: SettingsTab) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Chatbot Settings</h1>
        <p className="text-base text-slate-500 mt-1">Customize how your chatbot speaks and behaves.</p>
      </div>

      <div className="flex flex-col gap-6 md:flex-row md:gap-8">
        <SettingsNav active={tab} onChange={setTab} />

        <div className="max-w-2xl flex-1">
          {tab === 'personality' && (
            <PersonalitySection
              form={form}
              set={set}
              languages={languages}
              languageLabel={languageLabel}
              fallbackMessages={fallbackMessages}
              setFallbackMessageFor={setFallbackMessageFor}
              personalityMut={personalityMut}
            />
          )}
          {tab === 'appearance' && (
            <AppearanceSection
              customBrandingAllowed={customBrandingAllowed}
              color={color}
              setColor={setColor}
              isValidColor={isValidColor}
              colorMut={colorMut}
            />
          )}
          {tab === 'languages' && (
            <LanguagesSection
              languages={languages}
              maxLanguages={plan?.limits.max_languages ?? undefined}
              toggleLanguage={toggleLanguage}
              languagesMut={languagesMut}
            />
          )}
          {tab === 'booking' && (
            <BookingSection
              bookingEnabled={bookingEnabled}
              calendarBanner={calendarBanner}
              calendarStatus={calendarStatus}
              disconnectCalendarMut={disconnectCalendarMut}
              businessHours={businessHours}
              setDayHours={setDayHours}
              businessHoursMut={businessHoursMut}
            />
          )}
          {tab === 'advanced' && <AdvancedSection form={form} set={set} advancedMut={advancedMut} />}
        </div>
      </div>
    </div>
  )
}
