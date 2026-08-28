import { UseMutationResult } from '@tanstack/react-query'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Settings, FieldChangeEvent } from './types'

interface Props {
  form: Partial<Settings>
  set: (k: keyof Settings) => (e: FieldChangeEvent) => void
  languages: string[]
  languageLabel: (code: string) => string
  fallbackMessages: Record<string, string>
  setFallbackMessageFor: (code: string) => (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  personalityMut: UseMutationResult<unknown, unknown, void>
}

export function PersonalitySection({
  form,
  set,
  languages,
  languageLabel,
  fallbackMessages,
  setFallbackMessageFor,
  personalityMut,
}: Props) {
  return (
    <Card title="Personality">
      <div className="space-y-4">
        <div>
          <label className="block text-base font-medium text-slate-700 mb-1">Tone</label>
          <select
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.tone || 'friendly'}
            onChange={set('tone')}
          >
            {['friendly', 'formal', 'concise', 'playful'].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-base font-medium text-slate-700 mb-1">Welcome message</label>
          <textarea
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            rows={2}
            value={form.welcome_message || ''}
            onChange={set('welcome_message')}
          />
          <p className="text-sm text-slate-500 mt-1">
            Shown to every visitor as the opening greeting, before they've typed anything for the bot to
            go on — so it's always in this one language, regardless of which languages you enable below.
          </p>
        </div>
        <div>
          <label className="block text-base font-medium text-slate-700 mb-1">
            Fallback message {languages.length > 1 && `(${languageLabel(languages[0])})`}
          </label>
          <textarea
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            rows={2}
            value={form.fallback_message || ''}
            onChange={set('fallback_message')}
          />
          <p className="text-sm text-slate-500 mt-1">
            Shown when the bot can't find an answer, matched to the language{' '}
            {languages.length > 1 ? 'the visitor is writing in' : 'below'} — this is the{' '}
            {languages.length > 1 ? languageLabel(languages[0]) : 'default'} version, and also the
            fallback for any enabled language without its own translation below.
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
              Shown when a visitor writes in {languageLabel(code)}. Auto-filled with a translation when
              you enabled {languageLabel(code)} — edit it anytime, or leave blank to use the{' '}
              {languageLabel(languages[0])} message above instead.
            </p>
          </div>
        ))}
        <Button loading={personalityMut.isPending} onClick={() => personalityMut.mutate()}>
          Save personality
        </Button>
        {personalityMut.isSuccess && <p className="text-base text-green-600">Personality saved!</p>}
      </div>
    </Card>
  )
}
