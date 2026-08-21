// Minimal markdown renderer for chat replies: bold text, bullet/numbered
// lists, and paragraphs. Deliberately not a full CommonMark implementation —
// this covers what LLM responses actually produce, without pulling a markdown
// parser library into the widget's single embeddable bundle.

import type { ReactNode } from 'react'

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*.+?\*\*)/g).filter(Boolean)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>
  })
}

export function MarkdownText({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let listItems: string[] = []
  let listType: 'ul' | 'ol' | null = null

  const flushList = (key: string) => {
    if (!listItems.length || !listType) return
    const Tag = listType
    blocks.push(
      <Tag key={key} className={Tag === 'ul' ? 'list-disc pl-4 space-y-0.5' : 'list-decimal pl-4 space-y-0.5'}>
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item, `${key}-li-${i}`)}</li>
        ))}
      </Tag>
    )
    listItems = []
    listType = null
  }

  lines.forEach((line, idx) => {
    const bullet = line.match(/^\s*[-*]\s+(.*)/)
    const numbered = line.match(/^\s*\d+\.\s+(.*)/)

    if (bullet) {
      if (listType !== 'ul') flushList(`flush-${idx}`)
      listType = 'ul'
      listItems.push(bullet[1])
      return
    }
    if (numbered) {
      if (listType !== 'ol') flushList(`flush-${idx}`)
      listType = 'ol'
      listItems.push(numbered[1])
      return
    }

    flushList(`flush-${idx}`)
    if (line.trim()) {
      blocks.push(<p key={`p-${idx}`}>{renderInline(line, `p-${idx}`)}</p>)
    }
  })
  flushList('flush-end')

  return <div className="space-y-1.5">{blocks}</div>
}
