// Locale-aware display formatting. Only how a value LOOKS changes with the
// language -- stored values (dates, amounts, NOK prices) never do.

import { INTL_LOCALE, type Locale } from './core'

type DateInput = string | number | Date

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value)
}

const cache = new Map<string, Intl.DateTimeFormat | Intl.NumberFormat>()
function cached<T extends Intl.DateTimeFormat | Intl.NumberFormat>(key: string, make: () => T): T {
  let f = cache.get(key) as T | undefined
  if (!f) {
    f = make()
    cache.set(key, f)
  }
  return f
}

export function formatDate(locale: Locale, value: DateInput, style: 'short' | 'long' = 'short'): string {
  const opts: Intl.DateTimeFormatOptions =
    style === 'long' ? { day: 'numeric', month: 'long', year: 'numeric' } : { day: 'numeric', month: 'short', year: 'numeric' }
  return cached(`d:${locale}:${style}`, () => new Intl.DateTimeFormat(INTL_LOCALE[locale], opts)).format(toDate(value))
}

export function formatDateTime(locale: Locale, value: DateInput): string {
  return cached(
    `dt:${locale}`,
    () =>
      new Intl.DateTimeFormat(INTL_LOCALE[locale], {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }),
  ).format(toDate(value))
}

export function formatTime(locale: Locale, value: DateInput): string {
  return cached(`t:${locale}`, () => new Intl.DateTimeFormat(INTL_LOCALE[locale], { hour: '2-digit', minute: '2-digit' })).format(
    toDate(value),
  )
}

export function formatNumber(locale: Locale, value: number, maximumFractionDigits = 0): string {
  return cached(
    `n:${locale}:${maximumFractionDigits}`,
    () => new Intl.NumberFormat(INTL_LOCALE[locale], { maximumFractionDigits }),
  ).format(value)
}

export function formatPercent(locale: Locale, ratio: number): string {
  return cached(`p:${locale}`, () => new Intl.NumberFormat(INTL_LOCALE[locale], { style: 'percent', maximumFractionDigits: 0 })).format(
    ratio,
  )
}

/** A NOK amount, e.g. "NOK 1,490" in English and "1 490 kr" in Norwegian. */
export function formatNok(locale: Locale, amount: number): string {
  return locale === 'nb' ? `${formatNumber(locale, amount)} kr` : `NOK ${formatNumber(locale, amount)}`
}

/** An amount in a business's own currency (product prices); unknown codes fall back to "CODE 1.00". */
export function formatMoney(locale: Locale, amount: number, currency: string): string {
  try {
    return cached(
      `m:${locale}:${currency}`,
      () => new Intl.NumberFormat(INTL_LOCALE[locale], { style: 'currency', currency, minimumFractionDigits: 2 }),
    ).format(amount)
  } catch {
    return `${currency} ${formatNumber(locale, amount, 2)}`
  }
}

/** A language's name in the UI language, e.g. "no" -> "Norwegian" / "norsk". */
export function languageName(locale: Locale, code: string): string {
  try {
    const name = new Intl.DisplayNames([INTL_LOCALE[locale]], { type: 'language' }).of(code)
    return name ? name.charAt(0).toLocaleUpperCase(INTL_LOCALE[locale]) + name.slice(1) : code
  } catch {
    return code
  }
}
