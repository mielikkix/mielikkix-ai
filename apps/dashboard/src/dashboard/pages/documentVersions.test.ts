import { describe, expect, it } from 'vitest'
import { nameStem, olderVersions } from './documentVersions'

const doc = (id: string, filename: string, created_at: string, file_type = 'docx') => ({ id, filename, created_at, file_type })

describe('nameStem', () => {
  it('ignores extension, case, copy markers and dates', () => {
    for (const name of ['Pricing Comparison.docx', 'pricing-comparison (1).pdf', 'Pricing_Comparison_2026-10-05.docx', 'Pricing Comparison 05102026 v2.docx']) {
      expect(nameStem(name)).toBe('pricing comparison')
    }
  })

  it('keeps a language suffix, so translations are not versions', () => {
    expect(nameStem('FAQ-NO.docx')).not.toBe(nameStem('FAQ.docx'))
  })
})

describe('olderVersions', () => {
  it('flags every upload but the newest of the same name (QA 2026-10-08, A-08)', () => {
    const older = olderVersions([
      doc('a', 'FAQ.docx', '2026-10-02T10:00:00Z'),
      doc('b', 'FAQ.docx', '2026-10-05T10:00:00Z'),
      doc('c', 'FAQ-NO.docx', '2026-10-05T10:00:00Z'),
      doc('d', 'About.docx', '2026-10-02T10:00:00Z'),
    ])
    expect([...older.entries()]).toEqual([['a', 'FAQ.docx']])
  })

  it('leaves web pages alone', () => {
    const older = olderVersions([
      doc('a', 'https://example.com/', '2026-10-02T10:00:00Z', 'url'),
      doc('b', 'https://example.com/', '2026-10-05T10:00:00Z', 'url'),
    ])
    expect(older.size).toBe(0)
  })
})
