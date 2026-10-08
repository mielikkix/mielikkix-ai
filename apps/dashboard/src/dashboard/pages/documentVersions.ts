// Spots uploaded files that are older copies of a newer upload with the same
// name (QA 2026-10-08, A-08: the 02 Oct and 05 Oct versions of FAQ, Pricing
// Comparison etc. were all active at once, so outdated and current text
// competed in the chatbot's answers). "Pricing.docx", "pricing (1).pdf" and
// "Pricing_2026-10-05.docx" are one name; "Pricing-NO.docx" is a different
// (Norwegian) document, not an older version.

export interface VersionedDoc {
  id: string
  filename: string
  file_type: string
  created_at: string
}

const DATE_RE = /(?:\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d{2}[-_.]?\d{2}[-_.]?\d{4})/g

export function nameStem(filename: string): string {
  return filename
    .toLowerCase()
    .replace(/\.[a-z0-9]{1,5}$/, '') // extension
    .replace(DATE_RE, ' ')
    .replace(/\(\d+\)|\bcopy\b|\bkopi\b|[-_ ]v\d+\b|\bfinal\b/g, ' ')
    .replace(/[^a-z0-9æøå]+/g, ' ')
    .trim()
}

/** id of each older upload -> filename of the newest upload with the same name. */
export function olderVersions(docs: VersionedDoc[]): Map<string, string> {
  const groups = new Map<string, VersionedDoc[]>()
  for (const doc of docs) {
    if (doc.file_type === 'url') continue // a web page is re-fetched in place, never duplicated
    const stem = nameStem(doc.filename)
    if (!stem) continue
    groups.set(stem, [...(groups.get(stem) ?? []), doc])
  }
  const older = new Map<string, string>()
  for (const group of groups.values()) {
    if (group.length < 2) continue
    const sorted = [...group].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    for (const doc of sorted.slice(1)) older.set(doc.id, sorted[0].filename)
  }
  return older
}
