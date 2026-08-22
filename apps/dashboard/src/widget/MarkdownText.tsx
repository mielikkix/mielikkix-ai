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

function CodeBlock({ lines }: { lines: string[] }) {
  return (
    <pre className="bg-white border border-gray-200 rounded-lg p-2 text-xs font-mono overflow-x-auto">
      <code>{lines.join('\n')}</code>
    </pre>
  )
}

export function MarkdownText({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let listItems: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let listStart = 1
  let inCodeBlock = false
  let codeLines: string[] = []

  const flushList = (key: string) => {
    if (!listItems.length || !listType) return
    const Tag = listType
    blocks.push(
      <Tag
        key={key}
        start={Tag === 'ol' ? listStart : undefined}
        className={Tag === 'ul' ? 'list-disc pl-4 space-y-0.5' : 'list-decimal pl-4 space-y-0.5'}
      >
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item, `${key}-li-${i}`)}</li>
        ))}
      </Tag>
    )
    listItems = []
    listType = null
  }

  lines.forEach((line, idx) => {
    // Fenced code blocks (```lang ... ```) -- kept as raw text, no inline
    // bold/list parsing inside, since LLM replies use these for the embed
    // snippet and similar copy-pasteable content.
    if (/^\s*```/.test(line)) {
      if (!inCodeBlock) {
        flushList(`flush-${idx}`)
        inCodeBlock = true
        codeLines = []
      } else {
        blocks.push(<CodeBlock key={`code-${idx}`} lines={codeLines} />)
        inCodeBlock = false
        codeLines = []
      }
      return
    }
    if (inCodeBlock) {
      codeLines.push(line)
      return
    }

    const bullet = line.match(/^\s*[-*]\s+(.*)/)
    const numbered = line.match(/^\s*(\d+)\.\s+(.*)/)

    if (bullet) {
      if (listType !== 'ul') flushList(`flush-${idx}`)
      listType = 'ul'
      listItems.push(bullet[1])
      return
    }
    if (numbered) {
      if (listType !== 'ol') {
        flushList(`flush-${idx}`)
        listStart = Number(numbered[1])
      }
      listType = 'ol'
      listItems.push(numbered[2])
      return
    }

    flushList(`flush-${idx}`)
    if (line.trim()) {
      blocks.push(<p key={`p-${idx}`}>{renderInline(line, `p-${idx}`)}</p>)
    }
  })
  flushList('flush-end')
  // An unterminated fence (LLM cut off before closing ```) still renders
  // whatever was collected, rather than silently dropping it.
  if (inCodeBlock && codeLines.length) {
    blocks.push(<CodeBlock key="code-end" lines={codeLines} />)
  }

  return <div className="space-y-1.5">{blocks}</div>
}
