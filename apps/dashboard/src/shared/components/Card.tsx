import { ReactNode } from 'react'
import { clsx } from 'clsx'

interface Props {
  children: ReactNode
  className?: string
  title?: string
}

export function Card({ children, className, title }: Props) {
  return (
    <div className={clsx('bg-white rounded-2xl border border-slate-300 shadow-sm', className)}>
      {title && (
        <div className="border-b border-slate-100 px-6 py-4">
          <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  )
}
