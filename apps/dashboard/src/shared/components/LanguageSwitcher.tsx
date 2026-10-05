import { clsx } from 'clsx'
import { LOCALES, useT, type Locale } from '../i18n'
import { useAuthStore } from '../store/authStore'

// Two text buttons, "English" / "Norsk" (no flags: a language is not a
// country). Used before sign-in (AuthLayout) and inside the dashboard
// (Sidebar, Settings). Switching keeps the current page and any form state --
// it only re-renders the text -- and saves the choice on the user when signed in.
export function LanguageSwitcher({ className, compact = false }: { className?: string; compact?: boolean }) {
  const { t, locale } = useT()
  const changeLocale = useAuthStore((s) => s.changeLocale)

  return (
    <div role="group" aria-label={t('language.label')} className={clsx('inline-flex rounded-full border border-slate-200 bg-white p-0.5', className)}>
      {LOCALES.map((code: Locale) => {
        const active = code === locale
        return (
          <button
            key={code}
            type="button"
            lang={code}
            aria-pressed={active}
            onClick={() => void changeLocale(code)}
            className={clsx(
              'rounded-full font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
              compact ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm',
              active ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-slate-100',
            )}
          >
            {t(`language.${code}`)}
          </button>
        )
      })}
    </div>
  )
}
