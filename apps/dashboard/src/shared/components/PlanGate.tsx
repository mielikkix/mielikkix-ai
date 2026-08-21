import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Lock, Clock } from 'lucide-react'
import { usePlan, PlanFeatures, COMING_SOON_FEATURES } from '../hooks/usePlan'

interface Props {
  feature: keyof PlanFeatures
  children: ReactNode
  /** Render inline (e.g. wrapping a form field) instead of a full card. */
  inline?: boolean
}

/**
 * Shows children only if the current plan includes `feature`. Otherwise
 * renders an upgrade prompt (plan doesn't include it) or a "coming soon"
 * notice (plan includes it, but the feature isn't built yet -- see
 * COMING_SOON_FEATURES / backend NOT_YET_IMPLEMENTED_FEATURES).
 */
export function PlanGate({ feature, children, inline }: Props) {
  const { data: plan, isLoading } = usePlan()
  if (isLoading || !plan) return null

  const included = !!plan.features[feature]
  const comingSoon = COMING_SOON_FEATURES.has(feature as string)

  if (included && !comingSoon) return <>{children}</>

  if (!included) {
    return (
      <LockedNotice
        inline={inline}
        message={`Available on a higher plan.`}
      />
    )
  }

  return <LockedNotice inline={inline} message="Coming soon." icon={Clock} tone="neutral" />
}

function LockedNotice({
  message,
  inline,
  icon: Icon = Lock,
  tone = 'upgrade',
}: {
  message: string
  inline?: boolean
  icon?: typeof Lock
  tone?: 'upgrade' | 'neutral'
}) {
  const colors =
    tone === 'upgrade'
      ? 'border-brand-200 bg-brand-50 text-brand-700'
      : 'border-slate-200 bg-slate-50 text-slate-500'

  if (inline) {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm font-medium ${colors}`}>
        <Icon size={13} />
        {message}
        {tone === 'upgrade' && (
          <Link to="/dashboard/plan" className="underline">
            Upgrade
          </Link>
        )}
      </span>
    )
  }

  return (
    <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-base ${colors}`}>
      <Icon size={18} className="flex-shrink-0" />
      <span className="flex-1">{message}</span>
      {tone === 'upgrade' && (
        <Link to="/dashboard/plan" className="font-semibold underline flex-shrink-0">
          Upgrade
        </Link>
      )}
    </div>
  )
}
