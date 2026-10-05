import { UseMutationResult } from '@tanstack/react-query'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Settings, FieldChangeEvent } from './types'
import { useT } from '../../../shared/i18n'

// Stored tone values (the API's); only the labels are translated.
const TONES = ['friendly', 'formal', 'concise', 'playful'] as const

interface Props {
  form: Partial<Settings>
  set: (k: keyof Settings) => (e: FieldChangeEvent) => void
  languages: string[]
  languageLabel: (code: string) => string
  fallbackMessages: Record<string, string>
  setFallbackMessageFor: (code: string) => (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  welcomeMessages: Record<string, string>
  setWelcomeMessageFor: (code: string) => (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  personalityMut: UseMutationResult<unknown, unknown, void>
}

export function PersonalitySection({
  form,
  set,
  languages,
  languageLabel,
  fallbackMessages,
  setFallbackMessageFor,
  welcomeMessages,
  setWelcomeMessageFor,
  personalityMut,
}: Props) {
  const { t } = useT()
  const primary = languageLabel(languages[0])
  return (
    <Card title={t('settings.personality.title')}>
      <div className="space-y-4">
        <div>
          <label htmlFor="settings-tone" className="block text-base font-medium text-slate-700 mb-1">{t('settings.personality.tone')}</label>
          <select
            id="settings-tone"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.tone || 'friendly'}
            onChange={set('tone')}
          >
            {TONES.map((tone) => (
              <option key={tone} value={tone}>
                {t(`settings.personality.tones.${tone}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="settings-welcome" className="block text-base font-medium text-slate-700 mb-1">
            {languages.length > 1 ? t('settings.personality.welcomeFor', { language: primary }) : t('settings.personality.welcome')}
          </label>
          <textarea
            id="settings-welcome"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            rows={2}
            value={form.welcome_message || ''}
            onChange={set('welcome_message')}
          />
          <p className="text-sm text-slate-500 mt-1">
            {t('settings.personality.welcomeHelpBefore')}
            <code>&lt;html lang&gt;</code>
            {t('settings.personality.welcomeHelpAfter')}
            {languages.length > 1 && t('settings.personality.welcomeHelpPrimary', { language: primary })}
            {t('settings.personality.welcomeHelpEnd')}
          </p>
        </div>
        {languages.slice(1).map((code) => (
          <div key={`welcome-${code}`}>
            <label htmlFor={`settings-welcome-${code}`} className="block text-base font-medium text-slate-700 mb-1">
              {t('settings.personality.welcomeFor', { language: languageLabel(code) })}
            </label>
            <textarea
              id={`settings-welcome-${code}`}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              rows={2}
              placeholder={form.welcome_message || ''}
              value={welcomeMessages[code] || ''}
              onChange={setWelcomeMessageFor(code)}
            />
            <p className="text-sm text-slate-500 mt-1">
              {t('settings.personality.welcomeOtherHelp', { language: languageLabel(code), primary })}
            </p>
          </div>
        ))}
        <div>
          <label htmlFor="settings-fallback" className="block text-base font-medium text-slate-700 mb-1">
            {languages.length > 1 ? t('settings.personality.fallbackFor', { language: primary }) : t('settings.personality.fallback')}
          </label>
          <textarea
            id="settings-fallback"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            rows={2}
            value={form.fallback_message || ''}
            onChange={set('fallback_message')}
          />
          <p className="text-sm text-slate-500 mt-1">
            {languages.length > 1
              ? t('settings.personality.fallbackHelpMulti', { language: primary })
              : t('settings.personality.fallbackHelpSingle')}
          </p>
        </div>
        {languages.slice(1).map((code) => (
          <div key={code}>
            <label htmlFor={`settings-fallback-${code}`} className="block text-base font-medium text-slate-700 mb-1">
              {t('settings.personality.fallbackFor', { language: languageLabel(code) })}
            </label>
            <textarea
              id={`settings-fallback-${code}`}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              rows={2}
              placeholder={form.fallback_message || ''}
              value={fallbackMessages[code] || ''}
              onChange={setFallbackMessageFor(code)}
            />
            <p className="text-sm text-slate-500 mt-1">
              {t('settings.personality.fallbackOtherHelp', { language: languageLabel(code), primary })}
            </p>
          </div>
        ))}
        <Button loading={personalityMut.isPending} onClick={() => personalityMut.mutate()}>
          {t('settings.personality.save')}
        </Button>
        {personalityMut.isSuccess && <p role="status" className="text-base text-green-600">{t('settings.personality.saved')}</p>}
      </div>
    </Card>
  )
}
