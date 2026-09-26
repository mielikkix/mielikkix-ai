// Reactive layer on top of CurrencyService: holds the current selection + fetched rates in
// memory, notifies subscribers, and applies the current state to every [data-price-usd] node
// in the DOM. UI components (LanguageSwitcher, and the Layout bootstrap) talk to this module,
// never to CurrencyService or localStorage directly.
//
// Currency is currently driven entirely by the selected language (see SUPPORTED_LANGUAGES
// in translationService.ts) rather than chosen independently, so callers always pass the
// currency explicitly instead of this module reading its own stored preference.

import {
  setCurrency as persistCurrency,
  getExchangeRate,
  convertUSDToNOK,
  formatCurrency,
} from "../services/CurrencyService";
import { BASE_CURRENCY, type CurrencyCode } from "../config/currency";

export interface CurrencyState {
  currency: CurrencyCode;
  /** USD -> currency rates fetched so far this session, keyed by currency code. */
  rates: Partial<Record<CurrencyCode, number>>;
}

type Subscriber = (state: CurrencyState) => void;

let state: CurrencyState = { currency: BASE_CURRENCY, rates: {} };
const subscribers = new Set<Subscriber>();

/** Subscribes to state changes; immediately invoked once with the current state. Returns an unsubscribe function. */
export function subscribe(fn: Subscriber): () => void {
  subscribers.add(fn);
  fn(state);
  return () => subscribers.delete(fn);
}

function notify(): void {
  subscribers.forEach((fn) => fn(state));
}

function currentAmount(usdAmount: number): { value: number; currency: CurrencyCode } {
  if (state.currency === BASE_CURRENCY) return { value: usdAmount, currency: BASE_CURRENCY };

  const rate = state.rates[state.currency] ?? null;
  const converted = convertUSDToNOK(usdAmount, rate);
  // No rate available yet (cold cache, API down, no history) — show USD rather than break.
  return converted == null ? { value: usdAmount, currency: BASE_CURRENCY } : { value: converted, currency: state.currency };
}

function applyToDom(): void {
  if (typeof document === "undefined") return;
  document.querySelectorAll<HTMLElement>("[data-price-usd]").forEach((el) => {
    const usdAmount = Number(el.dataset.priceUsd);
    if (!Number.isFinite(usdAmount)) return;
    const { value, currency } = currentAmount(usdAmount);
    el.textContent = formatCurrency(value, currency);
  });
}

async function refreshRate(currency: CurrencyCode): Promise<void> {
  if (currency === BASE_CURRENCY || state.rates[currency] != null) return;
  const rate = await getExchangeRate(currency);
  if (rate == null) return;
  state = { ...state, rates: { ...state.rates, [currency]: rate } };
  applyToDom();
  notify();
}

/** Call once per page load with the currency for the currently-active language. Applies it and warms its rate in the background. */
export async function init(currency: CurrencyCode): Promise<void> {
  state = { currency, rates: {} };
  applyToDom();
  notify();
  await refreshRate(state.currency);
}

/** Called when the language (and therefore currency) changes. Persists the choice and applies it instantly (uses the cached rate if already warm). */
export function setCurrency(currency: CurrencyCode): void {
  persistCurrency(currency);
  state = { ...state, currency };
  applyToDom();
  notify();
  void refreshRate(currency);
}
