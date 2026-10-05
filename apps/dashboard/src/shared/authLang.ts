// Language of the public auth pages (sign-up, sign-in) -- QA 2026-10-05
// (BUG-15): the sign-up page was English-only, even when reached from the
// Norwegian marketing site. That site links here with ?lang=no; the choice is
// then remembered, and a toggle in AuthLayout changes it. The logged-in
// dashboard itself is English-only for now.
import { useSyncExternalStore } from 'react'
import { MARKETING_URL } from './legal'

export type AuthLang = 'en' | 'no'

const STORAGE_KEY = 'mielikkix:lang'
const EVENT = 'mielikkix:auth-lang'

function read(): AuthLang {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('lang')
    if (fromUrl === 'no' || fromUrl === 'en') {
      localStorage.setItem(STORAGE_KEY, fromUrl)
      return fromUrl
    }
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'no' || stored === 'en') return stored
  } catch {
    // Storage blocked: fall through to the browser language.
  }
  return /^(nb|nn|no)\b/i.test(navigator.language) ? 'no' : 'en'
}

export function setAuthLang(lang: AuthLang): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // Storage blocked: the switch still applies to this page view.
  }
  const url = new URL(window.location.href)
  url.searchParams.set('lang', lang)
  window.history.replaceState(null, '', url)
  window.dispatchEvent(new Event(EVENT))
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange)
  return () => window.removeEventListener(EVENT, onChange)
}

export function useAuthLang(): AuthLang {
  return useSyncExternalStore(subscribe, read, () => 'en')
}

/** A marketing-site page in the given language (the Norwegian copy lives under /no/). */
export function marketingUrl(path: string, lang: AuthLang): string {
  return `${MARKETING_URL}${lang === 'no' ? '/no' : ''}${path}`
}
