// React side of the dashboard's i18n: the current locale (zustand), how it is
// chosen and saved, and the useT() hook every screen uses.
//
// Which language is shown:
//   1. The signed-in user's saved preference (users.locale, from /auth/me).
//   2. Otherwise this browser's last choice (localStorage), or ?lang= from a
//      link (mielikkix.ai's Norwegian pages link to /register?lang=no).
//   3. Otherwise the browser's language, if it is Norwegian.
//   4. Otherwise English.
// Choosing a language while signed in also saves it on the user (see
// authStore's syncLocale), so it follows them to any device and login.

import { useCallback, useMemo } from 'react'
import { create } from 'zustand'
import { DEFAULT_LOCALE, isLocale, normalizeLocale, translate, translateOr, type Locale, type MessageKey, type Vars } from './core'
import * as fmt from './format'

export type { Locale, MessageKey, Vars } from './core'
export { LOCALES, translate } from './core'

const STORAGE_KEY = 'mielikkix:locale'
// Written by the earlier sign-up-only language toggle ("en"/"no").
const LEGACY_STORAGE_KEY = 'mielikkix:lang'

function readStored(): Locale | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isLocale(stored)) return stored
    return normalizeLocale(localStorage.getItem(LEGACY_STORAGE_KEY))
  } catch {
    return null
  }
}

function writeStored(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // Storage blocked: the choice still applies until the page is closed.
  }
}

/** The language to start with before /auth/me has answered. */
export function detectInitialLocale(): Locale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE
  const fromUrl = normalizeLocale(new URLSearchParams(window.location.search).get('lang'))
  if (fromUrl) {
    writeStored(fromUrl)
    return fromUrl
  }
  return readStored() ?? normalizeLocale(navigator.language) ?? DEFAULT_LOCALE
}

function applyDocumentLang(locale: Locale): void {
  if (typeof document !== 'undefined') document.documentElement.lang = locale
}

interface LocaleState {
  locale: Locale
  /** True once the visitor picked a language here (vs. detected/defaulted). */
  chosen: boolean
  /** Shows `locale` and remembers it in this browser. */
  setLocale: (locale: Locale, opts?: { chosen?: boolean }) => void
}

export const useLocaleStore = create<LocaleState>((set) => {
  const initial = detectInitialLocale()
  applyDocumentLang(initial)
  return {
    locale: initial,
    chosen: readStored() !== null,
    setLocale: (locale, opts) => {
      writeStored(locale)
      applyDocumentLang(locale)
      set((s) => ({ locale, chosen: opts?.chosen ?? s.chosen }))
    },
  }
})

/** For code outside React (stores, API helpers). */
export function currentLocale(): Locale {
  return useLocaleStore.getState().locale
}

export function t(key: MessageKey, vars?: Vars): string {
  return translate(currentLocale(), key, vars)
}

/** Translation and formatting bound to the current language; re-renders on change. */
export function useT() {
  const locale = useLocaleStore((s) => s.locale)
  const tr = useCallback((key: MessageKey, vars?: Vars) => translate(locale, key, vars), [locale])
  return useMemo(
    () => ({
      locale,
      t: tr,
      /** Label for an API code under `prefix` (e.g. 'reviews.topics'), or the code itself. */
      tCode: (prefix: string, code: string, vars?: Vars) => translateOr(locale, `${prefix}.${code}`, code, vars),
      formatDate: (value: string | number | Date, style?: 'short' | 'long') => fmt.formatDate(locale, value, style),
      formatDateTime: (value: string | number | Date) => fmt.formatDateTime(locale, value),
      formatTime: (value: string | number | Date) => fmt.formatTime(locale, value),
      formatNumber: (value: number, digits?: number) => fmt.formatNumber(locale, value, digits),
      formatPercent: (ratio: number) => fmt.formatPercent(locale, ratio),
      formatNok: (amount: number) => fmt.formatNok(locale, amount),
      formatMoney: (amount: number, currency: string) => fmt.formatMoney(locale, amount, currency),
      languageName: (code: string) => fmt.languageName(locale, code),
    }),
    [locale, tr],
  )
}

/** A marketing-site page in the current language (its Norwegian copy lives under /no/). */
export function marketingPath(locale: Locale, path: string): string {
  return `https://mielikkix.ai${locale === 'nb' ? '/no' : ''}${path}`
}
