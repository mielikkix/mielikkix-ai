import { X, Clock } from 'lucide-react'
import { Button } from '../../shared/components/Button'
import { PlanCatalogEntry } from '../../shared/hooks/usePlan'
import { useT } from '../../shared/i18n'

interface Props {
  plan: PlanCatalogEntry
  onClose: () => void
}

/**
 * Shown instead of the checkout flow on production, where no payment
 * processor is connected yet -- see CheckoutModal.tsx for why. Keeps
 * business owners from filling in card details for a charge that can't
 * actually be taken.
 */
export function PaymentComingSoonModal({ plan, onClose }: Props) {
  const { t } = useT()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t('payment.soonTitle')}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{t('payment.soonTitle')}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 text-slate-400" aria-label={t('common.close')}>
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div className="flex items-start gap-3 rounded-xl bg-brand-50 px-4 py-3 text-brand-700">
            <Clock size={18} className="mt-0.5 flex-shrink-0" />
            <p className="text-base">
              {t('payment.soonBefore')}
              <strong>{plan.name}</strong>
              {t('payment.soonAfter')}
            </p>
          </div>

          <Button className="w-full justify-center" onClick={onClose}>
            {t('payment.gotIt')}
          </Button>
        </div>
      </div>
    </div>
  )
}
