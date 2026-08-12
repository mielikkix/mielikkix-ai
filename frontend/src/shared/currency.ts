// Dashboard-side currency conversion for MielikkiX's own subscription pricing (Plan &
// Billing / Checkout). Mirrors website/src/services/CurrencyService.ts's approach (same free
// Frankfurter API, USD as the base currency all plan prices are authored in, localStorage rate
// caching) but adapted to this app's React Query + localStorage conventions instead of a
// custom pub/sub store. Unrelated to PlanFeatures.multi_currency, which is about the currencies
// a business's own chat widget quotes ITS customers in, not what a business pays MielikkiX in.

export type CurrencyCode = 'EUR' | 'USD' | 'NOK'

export interface CurrencyDefinition {
  code: CurrencyCode
  symbol: string
  locale: string
  flag: string
  name: string
}

export const CURRENCIES: Record<CurrencyCode, CurrencyDefinition> = {
  EUR: { code: 'EUR', symbol: '€', locale: 'en-IE', flag: '🇪🇺', name: 'Euro' },
  USD: { code: 'USD', symbol: '$', locale: 'en-US', flag: '🇺🇸', name: 'US Dollar' },
  NOK: { code: 'NOK', symbol: 'kr', locale: 'nb-NO', flag: '🇳🇴', name: 'Norwegian Krone' },
}

export const SUPPORTED_CURRENCIES: CurrencyDefinition[] = [CURRENCIES.EUR, CURRENCIES.USD, CURRENCIES.NOK]

/** All plan prices (price_usd) are authored in USD — every other currency is converted from this. */
export const BASE_CURRENCY: CurrencyCode = 'USD'

export const DEFAULT_CURRENCY: CurrencyCode = 'EUR'

const STORAGE_KEY = 'mielikkix_dashboard_currency'

function isSupportedCurrency(value: string | null): value is CurrencyCode {
  return !!value && value in CURRENCIES
}

export function getStoredCurrency(): CurrencyCode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return isSupportedCurrency(stored) ? stored : DEFAULT_CURRENCY
  } catch {
    return DEFAULT_CURRENCY
  }
}

export function setStoredCurrency(currency: CurrencyCode): void {
  try {
    localStorage.setItem(STORAGE_KEY, currency)
  } catch {
    /* storage unavailable — selection just won't survive a reload, not fatal */
  }
}

/**
 * Frankfurter (https://frankfurter.dev): free, no API key, CORS-enabled, ECB reference rates.
 * Same provider the marketing site uses, kept consistent so EUR/USD/NOK prices agree across
 * both apps. Never throws — a failed lookup returns null so callers can fall back to USD.
 */
export async function fetchExchangeRate(quote: CurrencyCode): Promise<number | null> {
  if (quote === BASE_CURRENCY) return 1
  try {
    const res = await fetch(`https://api.frankfurter.dev/v1/latest?base=${BASE_CURRENCY}&symbols=${quote}`)
    if (!res.ok) throw new Error(`Frankfurter request failed: HTTP ${res.status}`)
    const data = (await res.json()) as { rates?: Record<string, number> }
    const rate = data.rates?.[quote]
    return typeof rate === 'number' ? rate : null
  } catch (err) {
    console.warn(`[currency] Exchange rate fetch for ${quote} failed:`, err)
    return null
  }
}

const formatters = new Map<CurrencyCode, Intl.NumberFormat>()

function getFormatter(currency: CurrencyCode): Intl.NumberFormat {
  const cached = formatters.get(currency)
  if (cached) return cached
  const { locale, code } = CURRENCIES[currency]
  const formatter = new Intl.NumberFormat(locale, { style: 'currency', currency: code, maximumFractionDigits: 0 })
  formatters.set(currency, formatter)
  return formatter
}

/** Formats a whole-unit amount in the given currency, e.g. formatCurrency(24, "EUR") -> "€24". */
export function formatCurrency(amount: number, currency: CurrencyCode): string {
  return getFormatter(currency).format(amount)
}
