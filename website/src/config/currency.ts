// Central currency configuration. To add a new currency: add an entry to
// src/assets/currencies.json, then register it in SUPPORTED_CURRENCIES below (with a flag
// image path for the switcher — see public/flags/README.md). No other code changes are
// required — CurrencySwitcher.astro renders itself from this list, and CurrencyService/Price
// are generic over currency code.

import currencies from "../assets/currencies.json";

export type CurrencyCode = keyof typeof currencies;

export interface CurrencyDefinition {
  code: CurrencyCode;
  symbol: string;
  locale: string;
  /** Path to the flag image shown in the switcher (not an emoji, Windows won't render flag emoji as pictures). */
  flag: string;
  /** Full name, used for aria-labels. */
  name: string;
}

export const CURRENCIES = currencies as Record<CurrencyCode, { symbol: string; locale: string; code: CurrencyCode }>;

export const SUPPORTED_CURRENCIES: CurrencyDefinition[] = [
  { code: "EUR", symbol: CURRENCIES.EUR.symbol, locale: CURRENCIES.EUR.locale, flag: "/flags/eu.svg", name: "Euro" },
  { code: "USD", symbol: CURRENCIES.USD.symbol, locale: CURRENCIES.USD.locale, flag: "/flags/us.svg", name: "US Dollar" },
  { code: "NOK", symbol: CURRENCIES.NOK.symbol, locale: CURRENCIES.NOK.locale, flag: "/flags/no.svg", name: "Norwegian Krone" },
];

/** All conversions are always priced from this base — product prices are authored in USD. */
export const BASE_CURRENCY: CurrencyCode = "USD";

/** Site-wide default display currency — visitors can still switch to USD/NOK via CurrencySwitcher. */
export const DEFAULT_CURRENCY: CurrencyCode = "EUR";

/** Exchange rates are refreshed at most this often — keeps API calls to ~1/day site-wide. */
export const RATE_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export const STORAGE_KEYS = {
  CURRENCY: "mielikkix_currency",
  RATE_CACHE: "mielikkix_exchange_rate",
} as const;

export const CURRENCY_CHANGE_EVENT = "mielikkix:currencychange";
