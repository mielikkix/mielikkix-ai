import { UseMutationResult } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { AVAILABLE_LANGUAGES } from './types'
import { useT } from '../../../shared/i18n'

interface Props {
  languages: string[]
  // Raw plan limit, possibly undefined while the plan query is still
  // loading -- same "—" placeholder the original single-page Settings used
  // during that brief window, preserved here rather than defaulting to 1
  // for display (the gating logic below still needs a real number, so it
  // defaults separately).
  maxLanguages: number | undefined
  toggleLanguage: (code: string) => void
  languagesMut: UseMutationResult<unknown, unknown, string[]>
}

export function LanguagesSection({ languages, maxLanguages, toggleLanguage, languagesMut }: Props) {
  // undefined = plan not loaded yet (treat as 1); null limits arrive here as undefined too.
  const effectiveMax = maxLanguages ?? 1
  const { t, languageName } = useT()
  return (
    <Card title={t('settings.languages.title')}>
      <div className="space-y-3">
        <p className="text-sm text-slate-500">{t('settings.languages.intro')}</p>
        <p className="text-sm text-slate-500">
          {t('settings.languages.count', { count: languages.length, max: maxLanguages ?? 1 })}
        </p>
        <div className="flex flex-wrap gap-2">
          {AVAILABLE_LANGUAGES.map((code) => {
            const label = languageName(code)
            const active = languages.includes(code)
            const disabled = !active && languages.length >= effectiveMax
            return (
              <button
                key={code}
                type="button"
                disabled={disabled}
                aria-pressed={active}
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
        <Button size="sm" loading={languagesMut.isPending} onClick={() => languagesMut.mutate(languages)}>
          {t('settings.languages.save')}
        </Button>
        {languagesMut.isSuccess && <p role="status" className="text-base text-green-600">{t('settings.languages.saved')}</p>}
      </div>
    </Card>
  )
}
