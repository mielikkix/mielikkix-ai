import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { useAgentAccess } from '../hooks/usePlan'

interface Props {
  agentKey: string
  children: ReactNode
  /** Render inline (e.g. wrapping a form field) instead of a full card. */
  inline?: boolean
}

/**
 * Shows children only if this business has purchased `agentKey` (see
 * agent_access_service.py -- deliberately separate from PlanGate, since
 * agent access has nothing to do with the chat-widget plan).
 */
export function AgentGate({ agentKey, children, inline }: Props) {
  const { data: access, isLoading } = useAgentAccess()
  if (isLoading || !access) return null

  if (access[agentKey]) return <>{children}</>

  const message = 'Not active on your account yet.'

  if (inline) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-2.5 py-1 text-sm font-medium text-brand-700">
        <Lock size={13} />
        {message}
        <Link to="/dashboard/plan" className="underline">
          Contact us
        </Link>
      </span>
    )
  }

  return (
    <div className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-base text-brand-700">
      <Lock size={18} className="flex-shrink-0" />
      <span className="flex-1">{message}</span>
      <Link to="/dashboard/plan" className="font-semibold underline flex-shrink-0">
        Contact us
      </Link>
    </div>
  )
}
