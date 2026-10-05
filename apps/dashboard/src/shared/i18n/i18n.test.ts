// Run: npm test -- --run
import { describe, expect, it } from 'vitest'
import { en } from './locales/en'
import { nb } from './locales/nb'
import { INTL_LOCALE, messageKeys, normalizeLocale, translate, translateOr, type MessageKey } from './core'
import { formatDate, formatNok, formatNumber, languageName } from './format'
import { translateApiDetail } from './apiError'

const enKeys = messageKeys(en)
const nbKeys = new Set(messageKeys(nb))

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()

function leaf(tree: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], tree)
}

describe('message catalogs', () => {
  it('has a Norwegian message for every English key', () => {
    const missing = enKeys.filter((k) => !nbKeys.has(k))
    expect(missing).toEqual([])
  })

  it('has no Norwegian keys that English lacks (typos would silently fall back)', () => {
    const enSet = new Set(enKeys)
    expect([...nbKeys].filter((k) => !enSet.has(k))).toEqual([])
  })

  it('uses the same {placeholders} in both languages', () => {
    const mismatched = enKeys.filter((key) => {
      const e = leaf(en, key)
      const n = leaf(nb, key)
      const flat = (v: unknown) => (typeof v === 'string' ? [v] : Object.values(v as Record<string, string>))
      return flat(e).map(placeholders).join('|') !== flat(n).map(placeholders).join('|')
    })
    expect(mismatched).toEqual([])
  })

  it('never renders a raw key or an empty string, in either language', () => {
    for (const locale of ['en', 'nb'] as const) {
      for (const key of enKeys) {
        const text = translate(locale, key as MessageKey, { count: 2 })
        expect(text, `${locale}:${key}`).not.toBe('')
        expect(text, `${locale}:${key}`).not.toBe(key)
      }
    }
  })
})

describe('translate', () => {
  it('renders English and Norwegian', () => {
    expect(translate('en', 'navigation.settings')).toBe('Settings')
    expect(translate('nb', 'navigation.settings')).toBe('Innstillinger')
    expect(translate('nb', 'common.save')).toBe('Lagre')
  })

  it('fills placeholders without translating the values (customer data stays as entered)', () => {
    expect(translate('nb', 'leads.interestedIn', { interest: 'Booking Assistant' })).toBe('Interessert i: Booking Assistant')
    expect(translate('nb', 'checkout.title', { plan: 'Business' })).toBe('Oppgrader til Business')
  })

  it('picks singular and plural forms', () => {
    expect(translate('en', 'conversations.messages', { count: 1 })).toBe('1 message')
    expect(translate('en', 'conversations.messages', { count: 3 })).toBe('3 messages')
    expect(translate('nb', 'conversations.messages', { count: 1 })).toBe('1 melding')
    expect(translate('nb', 'conversations.messages', { count: 3 })).toBe('3 meldinger')
  })

  it('formats numeric placeholders for the language', () => {
    expect(translate('en', 'plan.features.conversations', { count: 1000 })).toBe('1,000 AI conversations/mo')
    expect(translate('nb', 'plan.features.conversations', { count: 1000 })).toBe(`1${' '}000 AI-samtaler/mnd`)
  })

  it('labels API codes, and shows an unknown code as itself', () => {
    expect(translateOr('nb', 'reviews.topics.waiting_time', 'waiting_time')).toBe('Ventetid')
    expect(translateOr('nb', 'reviews.topics.brand_new_topic', 'brand_new_topic')).toBe('brand_new_topic')
  })
})

describe('normalizeLocale', () => {
  it('maps every Norwegian tag to Bokmål and rejects others', () => {
    expect(normalizeLocale('no')).toBe('nb')
    expect(normalizeLocale('nb-NO')).toBe('nb')
    expect(normalizeLocale('nn')).toBe('nb')
    expect(normalizeLocale('en-US')).toBe('en')
    expect(normalizeLocale('de')).toBeNull()
    expect(normalizeLocale(null)).toBeNull()
  })
})

describe('formatting', () => {
  const date = new Date(2026, 9, 13, 9, 5)

  it('uses Norwegian date and number conventions without changing the value', () => {
    expect(INTL_LOCALE.nb).toBe('nb-NO')
    expect(formatDate('nb', date, 'long')).toBe('13. oktober 2026')
    expect(formatDate('en', date, 'long')).toBe('13 October 2026')
    expect(formatNumber('nb', 1234567)).toBe(`1${' '}234${' '}567`)
    expect(formatNumber('en', 1234567)).toBe('1,234,567')
  })

  it('keeps NOK as the currency in both languages', () => {
    expect(formatNok('nb', 1490)).toBe(`1${' '}490 kr`)
    expect(formatNok('en', 1490)).toBe('NOK 1,490')
  })

  it('names chatbot languages in the UI language', () => {
    expect(languageName('nb', 'no')).toBe('Norsk')
    expect(languageName('en', 'no')).toBe('Norwegian')
  })
})

describe('API errors', () => {
  it('translates known server messages and leaves unknown ones alone', () => {
    // currentLocale() is English in tests; the mapping itself is what is checked here.
    expect(translateApiDetail('Invalid credentials')).toBe('Invalid email or password.')
    expect(translateApiDetail('Value error, Password must be at least 10 characters long')).toBe(
      'The password must be at least 10 characters long.',
    )
    expect(translateApiDetail('File type .exe not supported')).toBe('Files of type .exe are not supported.')
    expect(translateApiDetail('Something nobody mapped')).toBeNull()
  })
})
