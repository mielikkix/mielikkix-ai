import { Link } from 'react-router-dom'
import { clsx } from 'clsx'

interface Props {
  label: string
  used: number
  /** null means unlimited on the current plan. */
  limit: number | null
}

/** Small usage-vs-limit bar used on Documents/Products/etc. to show how
 * close a business is to its plan's cap, with an upgrade nudge once full. */
export function UsageMeter({ label, used, limit }: Props) {
  if (limit === null) {
    return (
      <p className="text-sm text-slate-500">
        {label}: <span className="font-medium text-slate-700">{used}</span>{' '}
        <span className="text-slate-400">(unlimited on your plan)</span>
      </p>
    )
  }

  const pct = Math.min(100, Math.round((used / limit) * 100))
  const atLimit = used >= limit

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-500">
          {label}: <span className="font-medium text-slate-700">{used} / {limit}</span>
        </span>
        {atLimit && (
          <Link to="/dashboard/plan" className="font-semibold text-brand-600 underline">
            Upgrade for more
          </Link>
        )}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={clsx('h-full rounded-full transition-all', atLimit ? 'bg-red-500' : 'brand-gradient')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
