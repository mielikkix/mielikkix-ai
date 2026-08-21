import { InputHTMLAttributes, forwardRef, useId } from 'react'
import { clsx } from 'clsx'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, Props>(({ label, error, className, id, ...rest }, ref) => {
  const generatedId = useId()
  const inputId = id ?? generatedId
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-base font-medium text-slate-700 mb-1">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className={clsx(
          'w-full rounded-xl border px-3 py-2 text-base shadow-sm outline-none transition',
          error ? 'border-red-400 focus:ring-red-400' : 'border-slate-300 focus:border-brand-500 focus:ring-1 focus:ring-brand-500',
          className
        )}
        {...rest}
      />
      {error && <p className="mt-1 text-sm text-red-500">{error}</p>}
    </div>
  )
})
Input.displayName = 'Input'
