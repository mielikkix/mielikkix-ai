import type { ReactNode } from 'react'
import { marketingPath, useT } from '../../shared/i18n'
import { LanguageSwitcher } from '../../shared/components/LanguageSwitcher'

export function AuthLayout({
  children,
  cardClassName = 'max-w-sm',
  contentClassName = '',
}: {
  children: ReactNode
  cardClassName?: string
  contentClassName?: string
}) {
  const year = new Date().getFullYear()
  const { t, locale } = useT()

  // Marketing and legal pages open in the same language (Norwegian copies live under /no/).
  const navLinks = [
    { href: marketingPath(locale, '/features/'), label: t('navigation.features') },
    { href: marketingPath(locale, '/pricing/'), label: t('navigation.pricing') },
  ]
  // Shown on every auth page (Login, Register, password reset) -- GDPR Phase 2.
  const legalLinks = [
    { href: marketingPath(locale, '/privacy/'), label: t('navigation.privacy') },
    { href: marketingPath(locale, '/terms/'), label: t('navigation.terms') },
    { href: marketingPath(locale, '/cookies/'), label: t('navigation.cookies') },
  ]

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <a href={marketingPath(locale, '/')} className="text-xl font-bold tracking-tight text-slate-900">
            Mielikki<span className="brand-gradient-text">x</span>
          </a>
          <nav className="flex items-center gap-4 sm:gap-6">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="hidden text-sm font-medium text-slate-600 hover:text-brand-600 sm:inline">
                {link.label}
              </a>
            ))}
            {/* Language choice before sign-in (it carries over to the account). */}
            <LanguageSwitcher compact />
          </nav>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center p-4">
        <div className={`w-full ${cardClassName} bg-white rounded-2xl border border-slate-300 shadow-md p-8 ${contentClassName}`}>
          {children}
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-2 px-6 py-6 text-sm text-slate-400 sm:flex-row sm:justify-between">
          <span>&copy; {year} Mielikkix</span>
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-1">
            <a href={marketingPath(locale, '/')} className="hover:text-brand-600">{t('navigation.home')}</a>
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-brand-600">{link.label}</a>
            ))}
            {legalLinks.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-brand-600">{link.label}</a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  )
}
