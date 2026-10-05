// Framework-free i18n core for the dashboard: message lookup with English
// fallback, {placeholder} interpolation and plurals. React bindings (the
// locale store, useT) live in ./index.ts.
//
// Messages are plain nested objects (./locales/en/*.ts). English is complete
// by definition (it defines the key types); Norwegian may lack a key while a
// translation is being written -- the English text is shown instead, never
// the key itself, and tests/i18n.test.ts fails on any missing Norwegian key.

import { en } from './locales/en'
import { nb } from './locales/nb'

export type Locale = 'en' | 'nb'
export const LOCALES: readonly Locale[] = ['en', 'nb']
export const DEFAULT_LOCALE: Locale = 'en'

/** A message with a singular and plural form: t(key, { count }). */
export interface Plural {
  one: string
  other: string
}

type Messages = typeof en
type MessageNode = string | Plural | { [key: string]: MessageNode }

/** Every dot-path in the English messages that ends at a string or a plural. */
type Paths<T, P extends string = ''> = {
  [K in keyof T & string]: T[K] extends string
    ? `${P}${K}`
    : T[K] extends Plural
      ? `${P}${K}`
      : Paths<T[K], `${P}${K}.`>
}[keyof T & string]

export type MessageKey = Paths<Messages>
export type Vars = Record<string, string | number>

export type DeepPartial<T> = { [K in keyof T]?: T[K] extends string ? string : DeepPartial<T[K]> }

const MESSAGES: Record<Locale, unknown> = { en, nb }

/** BCP 47 tags for Intl formatting. */
export const INTL_LOCALE: Record<Locale, string> = { en: 'en-GB', nb: 'nb-NO' }

export function isLocale(value: unknown): value is Locale {
  return value === 'en' || value === 'nb'
}

/** "no", "nb-NO", "nn" -> "nb"; "en-US" -> "en"; anything else -> null. */
export function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) return null
  const base = value.trim().toLowerCase().split(/[-_]/)[0]
  if (base === 'nb' || base === 'no' || base === 'nn') return 'nb'
  if (base === 'en') return 'en'
  return null
}

function lookup(locale: Locale, key: string): MessageNode | undefined {
  let node: unknown = MESSAGES[locale]
  for (const part of key.split('.')) {
    if (node === null || typeof node !== 'object') return undefined
    node = (node as Record<string, unknown>)[part]
  }
  return node as MessageNode | undefined
}

function isPlural(node: unknown): node is Plural {
  return typeof node === 'object' && node !== null && 'other' in node && typeof (node as Plural).other === 'string'
}

const pluralRules = new Map<Locale, Intl.PluralRules>()
function pluralCategory(locale: Locale, count: number): 'one' | 'other' {
  let rules = pluralRules.get(locale)
  if (!rules) {
    rules = new Intl.PluralRules(INTL_LOCALE[locale])
    pluralRules.set(locale, rules)
  }
  return rules.select(count) === 'one' ? 'one' : 'other'
}

function resolve(locale: Locale, key: string, vars?: Vars): string | undefined {
  const node = lookup(locale, key)
  if (typeof node === 'string') return node
  if (isPlural(node)) {
    const count = typeof vars?.count === 'number' ? vars.count : Number(vars?.count ?? 0)
    return node[pluralCategory(locale, count)] ?? node.other
  }
  return undefined
}

let onMissing: (locale: Locale, key: string) => void = (locale, key) => {
  if (import.meta.env?.DEV) console.warn(`[i18n] Missing ${locale} message: ${key}`)
}

/** Tests replace this to fail on a missing message. */
export function setMissingHandler(handler: (locale: Locale, key: string) => void): void {
  onMissing = handler
}

/** Fills {name}-style placeholders. Numbers are formatted for the locale. */
function interpolate(locale: Locale, text: string, vars?: Vars): string {
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = vars[name]
    if (value === undefined) return match
    return typeof value === 'number' ? new Intl.NumberFormat(INTL_LOCALE[locale]).format(value) : value
  })
}

/**
 * The message for `key` in `locale`, falling back to English. Never returns
 * the key itself: a key missing in English too (only possible with an
 * unchecked cast) renders as an empty string and is reported.
 */
export function translate(locale: Locale, key: MessageKey, vars?: Vars): string {
  let text = resolve(locale, key, vars)
  if (text === undefined && locale !== DEFAULT_LOCALE) {
    onMissing(locale, key)
    text = resolve(DEFAULT_LOCALE, key, vars)
  }
  if (text === undefined) {
    onMissing(DEFAULT_LOCALE, key)
    return ''
  }
  return interpolate(locale, text, vars)
}

/**
 * For labels of codes that come from the API (statuses, topics...): the
 * message at `key` if one exists, else `fallback` (the raw code) -- a code
 * added server-side later shows as itself instead of an empty label.
 */
export function translateOr(locale: Locale, key: string, fallback: string, vars?: Vars): string {
  const text = resolve(locale, key, vars) ?? resolve(DEFAULT_LOCALE, key, vars)
  return text === undefined ? fallback : interpolate(locale, text, vars)
}

/** Every key path present in a message tree (used by the completeness test). */
export function messageKeys(tree: unknown, prefix = ''): string[] {
  if (typeof tree === 'string' || isPlural(tree)) return [prefix]
  if (tree === null || typeof tree !== 'object') return []
  return Object.entries(tree as Record<string, unknown>).flatMap(([k, v]) =>
    messageKeys(v, prefix ? `${prefix}.${k}` : k),
  )
}

export { MESSAGES }
