// A Norwegian message that is missing (e.g. a key added in English but not yet
// translated) must show the English text, never the key.
import { describe, expect, it, vi } from 'vitest'

vi.mock('./locales/nb', () => ({ nb: { common: { save: 'Lagre' } } }))

const { translate, setMissingHandler } = await import('./core')

describe('fallback to English', () => {
  it('shows English for a missing Norwegian message and reports it', () => {
    const missing: string[] = []
    setMissingHandler((locale, key) => missing.push(`${locale}:${key}`))

    expect(translate('nb', 'common.save')).toBe('Lagre')
    expect(translate('nb', 'common.cancel')).toBe('Cancel')
    expect(translate('nb', 'conversations.messages', { count: 2 })).toBe('2 messages')
    expect(missing).toEqual(['nb:common.cancel', 'nb:conversations.messages'])
  })
})
