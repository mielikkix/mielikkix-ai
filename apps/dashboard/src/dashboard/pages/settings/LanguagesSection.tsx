import { UseMutationResult } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { AVAILABLE_LANGUAGES } from './types'

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
  const effectiveMax = maxLanguages ?? 1
  return (
    <Card title="Languages">
      <div className="space-y-3">
        <p className="text-sm text-slate-500">
          {languages.length} / {maxLanguages ?? '—'} language{effectiveMax === 1 ? '' : 's'} selected
        </p>
        <div className="flex flex-wrap gap-2">
          {AVAILABLE_LANGUAGES.map(({ code, label }) => {
            const active = languages.includes(code)
            const disabled = !active && languages.length >= effectiveMax
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
        <Button size="sm" loading={languagesMut.isPending} onClick={() => languagesMut.mutate(languages)}>
          Save languages
        </Button>
        {languagesMut.isSuccess && <p className="text-base text-green-600">Languages saved!</p>}
      </div>
    </Card>
  )
}
