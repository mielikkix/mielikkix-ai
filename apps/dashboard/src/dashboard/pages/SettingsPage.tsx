import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { MessageCircle } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { PlanGate } from '../../shared/components/PlanGate'
import { usePlan } from '../../shared/hooks/usePlan'

interface Settings {
  tone: string
  welcome_message: string
  fallback_message: string
  fallback_messages: Record<string, string>
  contact_email: string | null
  contact_phone: string | null
  languages: string[]
  llm_provider: string
  llm_model: string | null
}

// Small curated list rather than every ISO code -- keeps the picker usable;
// extend as real demand shows up.
const AVAILABLE_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'no', label: 'Norwegian' },
  { code: 'de', label: 'German' },
  { code: 'fr', label: 'French' },
  { code: 'es', label: 'Spanish' },
  { code: 'it', label: 'Italian' },
  { code: 'nl', label: 'Dutch' },
  { code: 'pl', label: 'Polish' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'sv', label: 'Swedish' },
]

interface Business {
  primary_color: string
}

// Curated, brand-friendly palette — first entry matches the platform's own default.
const PRESET_COLORS = [
  '#ff6b00', // Orange (default)
  '#7c3aed', // Violet
  '#4f46e5', // Indigo
  '#2563eb', // Blue
  '#0d9488', // Teal
  '#059669', // Emerald
  '#d97706', // Amber
  '#e11d48', // Rose
  '#1e293b', // Slate
]

const HEX_COLOR_REGEX = /^#[0-9A-Fa-f]{6}$/

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

  const mut = useMutation({
    mutationFn: (body: Partial<Settings>) => api.patch('/businesses/me/settings', body),
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

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Chatbot Settings</h1>
        <p className="text-base text-slate-500 mt-1">Customize how your chatbot speaks and behaves.</p>
      </div>

      <Card title="Personality">
        <div className="space-y-4">
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">Tone</label>
            <select className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" value={form.tone || 'friendly'} onChange={set('tone')}>
              {['friendly', 'formal', 'concise', 'playful'].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">Welcome message</label>
            <textarea className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" rows={2}
              value={form.welcome_message || ''} onChange={set('welcome_message')} />
            <p className="text-sm text-slate-500 mt-1">
              Shown to every visitor as the opening greeting, before they've typed anything for the bot to go on — so it's always in this one language, regardless of which languages you enable below.
            </p>
          </div>
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">
              Fallback message {languages.length > 1 && `(${languageLabel(languages[0])})`}
            </label>
            <textarea className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" rows={2}
              value={form.fallback_message || ''} onChange={set('fallback_message')} />
            <p className="text-sm text-slate-500 mt-1">
              Shown when the bot can't find an answer, matched to the language {languages.length > 1 ? 'the visitor is writing in' : 'below'} — this is the {languages.length > 1 ? languageLabel(languages[0]) : 'default'} version, and also the fallback for any enabled language without its own translation below.
            </p>
          </div>
          {languages.slice(1).map((code) => (
            <div key={code}>
              <label className="block text-base font-medium text-slate-700 mb-1">
                Fallback message ({languageLabel(code)})
              </label>
              <textarea
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
                rows={2}
                placeholder={form.fallback_message || ''}
                value={fallbackMessages[code] || ''}
                onChange={setFallbackMessageFor(code)}
              />
              <p className="text-sm text-slate-500 mt-1">
                Shown when a visitor writes in {languageLabel(code)}. Auto-filled with a translation when you enabled {languageLabel(code)} — edit it anytime, or leave blank to use the {languageLabel(languages[0])} message above instead.
              </p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Widget Appearance">
        <div className="space-y-4">
          {!customBrandingAllowed && <PlanGate feature="custom_branding"><span /></PlanGate>}
          <div className={clsx(!customBrandingAllowed && 'pointer-events-none opacity-40')}>
            <div>
              <label className="block text-base font-medium text-slate-700 mb-2">Widget color</label>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Preset widget colors">
                {PRESET_COLORS.map((swatch) => {
                  const active = color.toLowerCase() === swatch.toLowerCase()
                  return (
                    <button
                      key={swatch}
                      type="button"
                      onClick={() => setColor(swatch)}
                      aria-label={`Use ${swatch}`}
                      aria-pressed={active}
                      className={clsx(
                        'h-8 w-8 rounded-full border-2 transition focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-500',
                        active ? 'border-slate-900 scale-110' : 'border-transparent hover:scale-105'
                      )}
                      style={{ backgroundColor: swatch }}
                    />
                  )
                })}
              </div>
            </div>

            <div className="flex items-end gap-4 mt-4">
              <div>
                <label htmlFor="custom-widget-color" className="block text-base font-medium text-slate-700 mb-1">
                  Custom color
                </label>
                <input
                  id="custom-widget-color"
                  type="color"
                  value={isValidColor ? color : '#ff6b00'}
                  onChange={(e) => setColor(e.target.value)}
                  aria-label="Pick a custom widget color"
                  className="h-10 w-14 cursor-pointer rounded-lg border border-slate-300"
                />
              </div>

              <Input
                label="Hex value"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                placeholder="#ff6b00"
                error={!isValidColor ? 'Enter a valid hex color, e.g. #ff6b00' : undefined}
                className="w-32"
              />

              <div className="flex flex-col items-center gap-1 pb-1">
                <span className="text-sm text-slate-500">Preview</span>
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-full text-white shadow-sm"
                  style={{ backgroundColor: isValidColor ? color : '#e2e8f0' }}
                >
                  <MessageCircle size={18} />
                </div>
              </div>
            </div>

            <Button className="mt-4" loading={colorMut.isPending} disabled={!isValidColor} onClick={() => colorMut.mutate(color)}>
              Save appearance
            </Button>
          </div>
          {colorMut.isSuccess && <p className="text-base text-green-600">Widget color saved!</p>}
          {colorMut.isError && (
            <p className="text-base text-red-600">
              {(colorMut.error as any)?.response?.data?.detail ?? 'Could not save widget color.'}
            </p>
          )}
        </div>
      </Card>

      <Card title="Languages">
        <div className="space-y-3">
          <p className="text-sm text-slate-500">
            {languages.length} / {plan?.limits.max_languages ?? '—'} language{maxLanguages === 1 ? '' : 's'} selected
          </p>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_LANGUAGES.map(({ code, label }) => {
              const active = languages.includes(code)
              const disabled = !active && languages.length >= maxLanguages
              return (
                <button
                  key={code}
                  type="button"
                  disabled={disabled}
                  onClick={() => toggleLanguage(code)}
                  className={clsx(
                    'rounded-full border px-3 py-1.5 text-sm font-medium transition',
                    active
                      ? 'brand-gradient border-transparent text-white'
                      : disabled
                        ? 'border-slate-200 text-slate-300 cursor-not-allowed'
                        : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                  )}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <Button
            size="sm"
            loading={languagesMut.isPending}
            onClick={() => languagesMut.mutate(languages)}
          >
            Save languages
          </Button>
          {languagesMut.isSuccess && <p className="text-base text-green-600">Languages saved!</p>}
        </div>
      </Card>

      <Card title="Contact info">
        <div className="space-y-3">
          <Input label="Contact email" type="email" value={form.contact_email || ''} onChange={set('contact_email')} />
          <Input label="Contact phone" value={form.contact_phone || ''} onChange={set('contact_phone')} />
        </div>
      </Card>

      <Card title="AI Provider">
        <div className="space-y-3">
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">LLM Provider</label>
            <select className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" value={form.llm_provider || 'groq'} onChange={set('llm_provider')}>
              {['groq', 'gemini', 'ollama'].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <Input label="Model name (optional)" value={form.llm_model || ''} onChange={set('llm_model')} placeholder="e.g. llama-3.1-8b-instant" />
        </div>
      </Card>

      <Button loading={mut.isPending} onClick={() => mut.mutate(form)}>Save settings</Button>
      {mut.isSuccess && <p className="text-base text-green-600">Settings saved!</p>}
    </div>
  )
}
