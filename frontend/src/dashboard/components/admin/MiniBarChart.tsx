import { useId, useState } from 'react'

interface Point {
  label: string
  value: number
}

interface Props {
  data: Point[]
  height?: number
  /** Formats the tooltip/value text, e.g. (v) => v.toLocaleString(). */
  formatValue?: (v: number) => string
  emptyMessage?: string
}

const VIEW_WIDTH = 600

/** Single-series daily bar chart (signups, token usage) -- thin bars, a
 * rounded data-end, a 2px surface gap between bars, and a hover tooltip.
 * One hue (brand-500) since this is always a single series -- no legend
 * needed (see the dataviz skill: a legend is for >=2 series). */
export function MiniBarChart({ data, height = 160, formatValue = (v) => v.toLocaleString(), emptyMessage = 'No data yet.' }: Props) {
  const gradientId = useId()
  const [hover, setHover] = useState<number | null>(null)

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-slate-400" style={{ height }}>
        {emptyMessage}
      </div>
    )
  }

  const max = Math.max(1, ...data.map((d) => d.value))
  const barGap = 2
  const barWidth = Math.max(2, VIEW_WIDTH / data.length - barGap)
  const chartHeight = height - 24 // leave room for x-axis labels

  // Show at most ~8 x-axis labels so dense ranges (e.g. 90 days) don't collide.
  const labelStride = Math.max(1, Math.ceil(data.length / 8))

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${height}`}
        className="w-full"
        style={{ height }}
        role="img"
        aria-label="Daily totals bar chart"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff974c" />
            <stop offset="100%" stopColor="#ff6b00" />
          </linearGradient>
        </defs>
        {/* Recessive baseline */}
        <line x1={0} y1={chartHeight} x2={VIEW_WIDTH} y2={chartHeight} stroke="#efe8e1" strokeWidth={1} />
        {data.map((d, i) => {
          const x = i * (barWidth + barGap)
          const barHeight = d.value === 0 ? 0 : Math.max(3, (d.value / max) * (chartHeight - 8))
          const y = chartHeight - barHeight
          const isHovered = hover === i
          return (
            <g key={d.label}>
              {/* Wider invisible hit target than the visible bar, per the skill's interaction guidance. */}
              <rect
                x={x - barGap / 2}
                y={0}
                width={barWidth + barGap}
                height={chartHeight}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                rx={Math.min(4, barWidth / 2)}
                fill={isHovered ? '#e05e00' : `url(#${gradientId})`}
                pointerEvents="none"
              />
              {i % labelStride === 0 && (
                <text
                  x={x + barWidth / 2}
                  y={height - 6}
                  textAnchor="middle"
                  fontSize={10}
                  fill="#9d9994"
                >
                  {d.label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {hover !== null && (
        <div className="mt-1 text-center text-sm text-slate-600">
          <span className="font-semibold text-slate-800">{data[hover].label}</span>: {formatValue(data[hover].value)}
        </div>
      )}
    </div>
  )
}
