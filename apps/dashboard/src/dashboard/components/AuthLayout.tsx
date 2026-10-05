import type { ReactNode } from 'react'
import { MARKETING_URL } from '../../shared/legal'
import { marketingUrl, setAuthLang, useAuthLang, type AuthLang } from '../../shared/authLang'

const LABELS: Record<AuthLang, Record<'features' | 'pricing' | 'home' | 'privacy' | 'terms' | 'cookies' | 'language', string>> = {
  en: { features: 'Features', pricing: 'Pricing', home: 'Home', privacy: 'Privacy', terms: 'Terms', cookies: 'Cookies', language: 'Language' },
  no: { features: 'Funksjoner', pricing: 'Priser', home: 'Hjem', privacy: 'Personvern', terms: 'Vilkår', cookies: 'Informasjonskapsler', language: 'Språk' },
}

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
  const lang = useAuthLang()
  const l = LABELS[lang]

  const navLinks = [
    { href: marketingUrl('/features/', lang), label: l.features },
    { href: marketingUrl('/pricing/', lang), label: l.pricing },
  ]
  // Shown on every auth page (Login, Register, password reset) -- GDPR Phase 2.
  const legalLinks = [
    { href: marketingUrl('/privacy/', lang), label: l.privacy },
    { href: marketingUrl('/terms/', lang), label: l.terms },
    { href: marketingUrl('/cookies/', lang), label: l.cookies },
  ]

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <a href={lang === 'no' ? `${MARKETING_URL}/no/` : MARKETING_URL} className="text-xl font-bold tracking-tight text-slate-900">
            Mielikki<span className="brand-gradient-text">x</span>
          </a>
          <nav className="flex items-center gap-6">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="text-sm font-medium text-slate-600 hover:text-brand-600">
                {link.label}
              </a>
            ))}
            <div role="group" aria-label={l.language} className="flex overflow-hidden rounded-full border border-slate-200 text-xs font-semibold">
              {(['en', 'no'] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  aria-pressed={lang === code}
                  onClick={() => setAuthLang(code)}
                  className={`px-2.5 py-1 ${lang === code ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                >
                  {code === 'no' ? 'NOR' : 'EN'}
                </button>
              ))}
            </div>
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
            <a href={lang === 'no' ? `${MARKETING_URL}/no/` : MARKETING_URL} className="hover:text-brand-600">{l.home}</a>
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
