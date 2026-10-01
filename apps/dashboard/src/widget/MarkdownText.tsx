// Minimal markdown renderer for chat replies: bold text, bullet/numbered
// lists, pipe tables, and paragraphs. Deliberately not a full CommonMark implementation —
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

const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
const isTableSeparator = (row: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(row)

// Pipe tables: LLMs use them for price comparisons ("which Business plan?"),
// and unrendered they showed as raw "| Produkt | ... |" lines in the widget.
function Table({ rows, keyPrefix }: { rows: string[]; keyPrefix: string }) {
  const [head, ...body] = rows.filter((r) => !isTableSeparator(r)).map(cells)
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {head.map((c, i) => (
              <th key={i} className="border-b border-gray-300 px-1.5 py-1 text-left font-semibold">
                {renderInline(c, `${keyPrefix}-h-${i}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, r) => (
            <tr key={r}>
              {row.map((c, i) => (
                <td key={i} className="border-b border-gray-200 px-1.5 py-1 align-top">
                  {renderInline(c, `${keyPrefix}-${r}-${i}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
  let tableRows: string[] = []

  const flushTable = (key: string) => {
    if (!tableRows.length) return
    // A lone "| x |" line isn't a table -- keep it as a paragraph.
    if (tableRows.length < 2) blocks.push(<p key={key}>{renderInline(tableRows[0], key)}</p>)
    else blocks.push(<Table key={key} rows={tableRows} keyPrefix={key} />)
    tableRows = []
  }

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
        flushTable(`table-${idx}`)
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

    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushList(`flush-${idx}`)
      tableRows.push(line)
      return
    }
    flushTable(`table-${idx}`)

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
  flushTable('table-end')
  // An unterminated fence (LLM cut off before closing ```) still renders
  // whatever was collected, rather than silently dropping it.
  if (inCodeBlock && codeLines.length) {
    blocks.push(<CodeBlock key="code-end" lines={codeLines} />)
  }

  return <div className="space-y-1.5">{blocks}</div>
}
