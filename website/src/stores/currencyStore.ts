// Reactive layer on top of CurrencyService: holds the current selection + fetched rates in
// memory, notifies subscribers, and applies the current state to every [data-price-nok] node
// (see Price.astro) and [data-currency-note] node in the DOM. UI components (CurrencySwitcher,
// LanguageSwitcher, and the Layout bootstrap) talk to this module, never to CurrencyService or
// localStorage directly.
//
// The currency follows the selected language by default (see SUPPORTED_LANGUAGES in
// translationService.ts) until the visitor picks one in CurrencySwitcher; from then on that
// choice is remembered and a language switch no longer touches it (QA 2026-10-01, B15:
// choosing USD, then Norsk, silently switched prices back to NOK).

import {
  setCurrency as persistCurrency,
  getStoredCurrency,
  getExchangeRate,
  convertFromNok,
  formatCurrency,
  roundForDisplay,
} from "../services/CurrencyService";
import { BASE_CURRENCY, type CurrencyCode } from "../config/currency";

export interface CurrencyState {
  currency: CurrencyCode;
  /** NOK -> currency rates fetched so far this session, keyed by currency code. */
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

function applyToDom(): void {
  if (typeof document === "undefined") return;
  const rate = state.currency === BASE_CURRENCY ? null : (state.rates[state.currency] ?? null);
  // No rate available yet (cold cache, API down, no history) — keep NOK rather than break.
  const converting = rate != null;

  // SVGElement too: the pricing chart's bar labels are <tspan>s.
  document.querySelectorAll<HTMLElement | SVGElement>("[data-price-nok]").forEach((el) => {
    // The server-rendered NOK text is the source of truth; keep it to restore when switching back.
    if (el.dataset.nokText === undefined) el.dataset.nokText = el.textContent ?? "";
    const nok = Number(el.dataset.priceNok);
    let converted = converting && Number.isFinite(nok) ? convertFromNok(nok, rate) : null;
    // Incl.-VAT price: VAT on the ex-VAT amount as displayed, so the two figures agree (see Price.astro).
    const vatRate = Number(el.dataset.vatRate);
    if (converted != null && vatRate > 0) converted = roundForDisplay(converted) * (1 + vatRate);
    el.textContent =
      converted == null ? el.dataset.nokText : formatCurrency(converted, state.currency, el.dataset.lang ?? "en");
  });

  document.querySelectorAll<HTMLElement>("[data-currency-note]").forEach((el) => {
    el.hidden = !converting;
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

/** Call once per page load with the visitor's currency. Applies it and warms its rate in the background. */
export async function init(currency: CurrencyCode): Promise<void> {
  state = { currency, rates: {} };
  applyToDom();
  notify();
  await refreshRate(state.currency);
}

function apply(currency: CurrencyCode): void {
  state = { ...state, currency };
  applyToDom();
  notify();
  void refreshRate(currency);
}

/** Called from CurrencySwitcher: the visitor's explicit choice. Persists it and applies it instantly (uses the cached rate if already warm). */
export function setCurrency(currency: CurrencyCode): void {
  persistCurrency(currency);
  apply(currency);
}

/** Called when the language changes: follows that language's currency, unless the visitor has picked one themselves. Not persisted. */
export function followLanguageCurrency(currency: CurrencyCode): void {
  if (getStoredCurrency() !== null) return;
  apply(currency);
}
