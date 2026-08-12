// Client-side i18n runtime: registry, storage, lazy-loaded + cached JSON translations,
// dot-path lookup, and DOM application. English is always server-rendered (the default,
// crawlable) content; this module only runs when a visitor has a non-default language
// stored, or when they click the language switcher.
//
// To add a new language: add a folder under src/assets/i18n/<code>/ with the same five
// JSON files as src/assets/i18n/en/, then add one entry to SUPPORTED_LANGUAGES below.

import type { CurrencyCode } from "../../config/currency";

export type LanguageCode = "en" | "no";

export interface LanguageDefinition {
  code: LanguageCode;
  /** Short label shown in the switcher, e.g. "EN" */
  label: string;
  /** Full name, used for aria attributes */
  name: string;
  /** Path to the flag image shown in the dropdown (see public/flags/README.md — not an emoji, Windows won't render flag emoji as pictures). */
  flag: string;
  /** Currency shown when this language is active — language and currency switch together as one control. */
  currency: CurrencyCode;
}

export const SUPPORTED_LANGUAGES: LanguageDefinition[] = [
  { code: "en", label: "EN", name: "English", flag: "/flags/gb.svg", currency: "EUR" },
  { code: "no", label: "NOR", name: "Norsk", flag: "/flags/no.svg", currency: "NOK" },
];

export const DEFAULT_LANGUAGE: LanguageCode = "en";

const STORAGE_KEY = "mielikkix:lang";
export const LANG_CHANGE_EVENT = "mielikkix:langchange";
const TITLE_SUFFIX = " · MielikkiX";

type TranslationDict = Record<string, unknown>;

// Vite code-splits every JSON file into its own lazy chunk — only the language/page
// combination actually requested is ever fetched.
const jsonModules = import.meta.glob<{ default: TranslationDict }>("/src/assets/i18n/*/*.json");

const cache = new Map<string, TranslationDict>();

function isSupportedLanguage(value: string | null): value is LanguageCode {
  return !!value && SUPPORTED_LANGUAGES.some((lang) => lang.code === value);
}

export function getStoredLanguage(): LanguageCode {
  if (typeof localStorage === "undefined") return DEFAULT_LANGUAGE;
  const stored = localStorage.getItem(STORAGE_KEY);
  return isSupportedLanguage(stored) ? stored : DEFAULT_LANGUAGE;
}

export function setStoredLanguage(lang: LanguageCode): void {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(STORAGE_KEY, lang);
}

async function loadNamespace(lang: LanguageCode, namespace: string): Promise<TranslationDict> {
  const cacheKey = `${lang}:${namespace}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const path = `/src/assets/i18n/${lang}/${namespace}.json`;
  const importer = jsonModules[path];
  if (!importer) {
    console.warn(`[i18n] Missing translation file: ${path}`);
    return {};
  }

  const mod = await importer();
  const dict = mod.default;
  cache.set(cacheKey, dict);
  return dict;
}

/**
 * Loads and merges the translation namespaces needed for a page: always "common" and
 * "footer" (shared on every page via Header/Footer), plus the given page namespace.
 */
export async function loadTranslations(lang: LanguageCode, page?: string): Promise<TranslationDict> {
  const namespaces = ["common", "footer", ...(page ? [page] : [])];
  const dicts = await Promise.all(namespaces.map((ns) => loadNamespace(lang, ns)));
  return Object.assign({}, ...dicts);
}

/** Dot-path lookup, e.g. t(dict, "NAV.FEATURES"). Falls back to the key itself if missing. */
export function t(dict: TranslationDict, key: string): string {
  const value = key.split(".").reduce<unknown>((acc, segment) => {
    if (acc !== null && typeof acc === "object" && segment in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[segment];
    }
    return undefined;
  }, dict);
  return typeof value === "string" ? value : key;
}

function applyTextNodes(dict: TranslationDict): void {
  document.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    el.textContent = t(dict, key).replace("{{YEAR}}", String(new Date().getFullYear()));
  });
}

function applyAttributes(dict: TranslationDict): void {
  document.querySelectorAll<HTMLElement>("[data-i18n-attr]").forEach((el) => {
    const spec = el.getAttribute("data-i18n-attr");
    if (!spec) return;
    spec.split(";").forEach((pair) => {
      const [attr, key] = pair.split(":").map((part) => part.trim());
      if (!attr || !key) return;
      el.setAttribute(attr, t(dict, key));
    });
  });
}

function applyDocTitle(dict: TranslationDict): void {
  const el = document.querySelector<HTMLElement>("[data-i18n-doc-title]");
  const key = el?.getAttribute("data-i18n-doc-title");
  if (key) document.title = `${t(dict, key)}${TITLE_SUFFIX}`;
}

function applyMetaTitles(dict: TranslationDict): void {
  document.querySelectorAll<HTMLMetaElement>("[data-i18n-meta-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-meta-title");
    if (key) el.setAttribute("content", `${t(dict, key)}${TITLE_SUFFIX}`);
  });
}

function applyMetaDescriptions(dict: TranslationDict): void {
  document.querySelectorAll<HTMLMetaElement>("[data-i18n-meta-desc]").forEach((el) => {
    const key = el.getAttribute("data-i18n-meta-desc");
    if (key) el.setAttribute("content", t(dict, key));
  });
}

export function applyTranslations(dict: TranslationDict, lang: LanguageCode): void {
  document.documentElement.lang = lang;
  applyTextNodes(dict);
  applyAttributes(dict);
  applyDocTitle(dict);
  applyMetaTitles(dict);
  applyMetaDescriptions(dict);
}

function dispatchLangChange(lang: LanguageCode): void {
  document.dispatchEvent(new CustomEvent(LANG_CHANGE_EVENT, { detail: { lang } }));
}

/** Call once per page load. No-ops (and stays zero-cost) when the stored language is the default. */
export async function initI18n(page?: string): Promise<void> {
  const lang = getStoredLanguage();
  if (lang !== DEFAULT_LANGUAGE) {
    const dict = await loadTranslations(lang, page);
    applyTranslations(dict, lang);
    dispatchLangChange(lang);
  }
  document.documentElement.classList.remove("i18n-loading");
}

/**
 * Called by the language switcher. Persists the choice and applies it instantly, no
 * navigation — including switching back to English, which re-applies the English JSON
 * rather than reloading, since the DOM may already hold another language's text.
 */
export async function switchLanguage(lang: LanguageCode, page?: string): Promise<void> {
  setStoredLanguage(lang);
  const dict = await loadTranslations(lang, page);
  applyTranslations(dict, lang);
  dispatchLangChange(lang);
}
