// Owns everything currency-related that isn't UI: calling the exchange rate API, caching
// rates in localStorage (~1 request/day/currency), the API-failure fallback chain, the
// selected-currency persistence, and formatting. UI (CurrencySwitcher, Price) never talks to
// the network or localStorage directly — it goes through currencyStore.ts, which calls here.

import { BASE_CURRENCY, RATE_CACHE_TTL_MS, STORAGE_KEYS, type CurrencyCode } from "../config/currency";
import { formatCurrency as formatCurrencyValue } from "../utils/currencyFormatter";

export interface ExchangeRateProvider {
  /** Resolves to the number of `quote` units per 1 `base` unit. */
  fetchRate(base: string, quote: string): Promise<number>;
}

/**
 * Frankfurter (https://frankfurter.dev): free, no API key, CORS-enabled, ECB reference
 * rates. Chosen as the default because this is a static site with no server to hide a key
 * behind — "Google's Exchange Rate API" isn't a real public API for third-party use.
 */
class FrankfurterProvider implements ExchangeRateProvider {
  async fetchRate(base: string, quote: string): Promise<number> {
    const res = await fetch(`https://api.frankfurter.dev/v1/latest?base=${base}&symbols=${quote}`);
    if (!res.ok) throw new Error(`Frankfurter request failed: HTTP ${res.status}`);
    const data = (await res.json()) as { rates?: Record<string, number> };
    const rate = data.rates?.[quote];
    if (typeof rate !== "number") throw new Error(`Frankfurter response missing rate for ${quote}`);
    return rate;
  }
}

// Swap the exchange rate provider here (e.g. for ExchangeRate-API, Open Exchange Rates,
// Fixer.io) — every other module (store, Price, CurrencySwitcher) only knows about
// getExchangeRate()/convertUSDToNOK() below, never about a specific provider.
const activeProvider: ExchangeRateProvider = new FrankfurterProvider();

interface RateCacheEntry {
  rate: number;
  timestamp: number;
}

function rateCacheKey(quote: CurrencyCode): string {
  return `${STORAGE_KEYS.RATE_CACHE}_${quote}`;
}

function readRateCache(quote: CurrencyCode): RateCacheEntry | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(rateCacheKey(quote));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<RateCacheEntry>;
    if (typeof parsed.rate !== "number" || typeof parsed.timestamp !== "number") return null;
    return parsed as RateCacheEntry;
  } catch {
    return null;
  }
}

function writeRateCache(quote: CurrencyCode, rate: number): void {
  if (typeof localStorage === "undefined") return;
  try {
    const entry: RateCacheEntry = { rate, timestamp: Date.now() };
    localStorage.setItem(rateCacheKey(quote), JSON.stringify(entry));
  } catch {
    /* storage unavailable/full — rate just won't survive a reload, not fatal */
  }
}

function isFresh(entry: RateCacheEntry): boolean {
  return Date.now() - entry.timestamp < RATE_CACHE_TTL_MS;
}

const inFlight = new Map<CurrencyCode, Promise<number | null>>();

/**
 * Returns the current base->quote exchange rate, or null if none could be obtained at all
 * (API unreachable and no cache ever existed). Never throws: a failed rate lookup must never
 * break the page, only fall back to showing USD.
 */
export async function getExchangeRate(quote: CurrencyCode): Promise<number | null> {
  if (quote === BASE_CURRENCY) return 1;

  const cached = readRateCache(quote);
  if (cached && isFresh(cached)) return cached.rate;

  const pending = inFlight.get(quote);
  if (pending) return pending;

  const request = (async (): Promise<number | null> => {
    try {
      const rate = await activeProvider.fetchRate(BASE_CURRENCY, quote);
      writeRateCache(quote, rate);
      return rate;
    } catch (err) {
      console.warn(`[currency] Exchange rate fetch for ${quote} failed, falling back to cache:`, err);
      return cached ? cached.rate : null;
    } finally {
      inFlight.delete(quote);
    }
  })();

  inFlight.set(quote, request);
  return request;
}

/** Converts a USD amount using the given rate. A null rate (unavailable) yields null — the caller shows USD instead. */
export function convertUSDToNOK(amountUsd: number, rate: number | null): number | null {
  if (rate == null) return null;
  return Math.round(amountUsd * rate);
}

export function formatCurrency(amount: number, currency: CurrencyCode): string {
  return formatCurrencyValue(amount, currency);
}

export function setCurrency(currency: CurrencyCode): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEYS.CURRENCY, currency);
  } catch {
    /* storage unavailable — selection just won't persist across reloads */
  }
}
