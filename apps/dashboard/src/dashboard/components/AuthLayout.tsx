import type { ReactNode } from 'react'
import { LEGAL_URLS, MARKETING_URL } from '../../shared/legal'

const navLinks = [
  { href: `${MARKETING_URL}/features`, label: 'Features' },
  { href: `${MARKETING_URL}/pricing`, label: 'Pricing' },
]

// Shown on every auth page (Login, Register, password reset) -- GDPR Phase 2.
const legalLinks = [
  { href: LEGAL_URLS.privacy, label: 'Privacy' },
  { href: LEGAL_URLS.terms, label: 'Terms' },
  { href: LEGAL_URLS.cookies, label: 'Cookies' },
]

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

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <a href={MARKETING_URL} className="text-xl font-bold tracking-tight text-slate-900">
            Mielikki<span className="brand-gradient-text">X</span>
          </a>
          <nav className="flex items-center gap-6">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="text-sm font-medium text-slate-600 hover:text-brand-600">
                {link.label}
              </a>
            ))}
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
            <a href={MARKETING_URL} className="hover:text-brand-600">Home</a>
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
