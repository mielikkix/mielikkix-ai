import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Lock, CreditCard } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { PlanCatalogEntry } from '../../shared/hooks/usePlan'

interface Props {
  plan: PlanCatalogEntry
  format: (usd: number) => string
  onClose: () => void
}

function formatCardNumber(raw: string) {
  const digits = raw.replace(/\D/g, '').slice(0, 16)
  return digits.replace(/(.{4})/g, '$1 ').trim()
}

function formatExpiry(raw: string) {
  const digits = raw.replace(/\D/g, '').slice(0, 4)
  return digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits
}

// Luhn checksum -- catches obvious typos without needing a real card
// network to validate against.
function passesLuhnCheck(digits: string) {
  let sum = 0
  let shouldDouble = false
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = parseInt(digits[i], 10)
    if (shouldDouble) {
      d *= 2
      if (d > 9) d -= 9
    }
    sum += d
    shouldDouble = !shouldDouble
  }
  return digits.length > 0 && sum % 10 === 0
}

function validateExpiry(mmYY: string): string | null {
  const match = /^(\d{2})\/(\d{2})$/.exec(mmYY)
  if (!match) return 'Enter expiry as MM/YY'
  const month = parseInt(match[1], 10)
  const year = 2000 + parseInt(match[2], 10)
  if (month < 1 || month > 12) return 'Enter a valid month'
  const now = new Date()
  const lastDayOfExpiryMonth = new Date(year, month, 0)
  if (lastDayOfExpiryMonth < new Date(now.getFullYear(), now.getMonth(), 1)) return 'Card has expired'
  return null
}

/**
 * Checkout screen shown before switching to a paid plan.
 *
 * IMPORTANT: no real payment gateway (Stripe, PayPal, etc.) is wired up
 * anywhere in this app yet -- there's no backend endpoint that accepts or
 * stores card details, and this form never sends any of these fields
 * anywhere. It exists to complete the upgrade UX and validate input
 * shape; the "payment" is simulated client-side, then the existing
 * PATCH /businesses/me/plan endpoint is called to actually switch plans.
 * Swap the fake delay below for a real Stripe Elements/Checkout
 * integration when a payment processor is actually connected.
 */
export function CheckoutModal({ plan, format, onClose }: Props) {
  const qc = useQueryClient()
  const [cardName, setCardName] = useState('')
  const [cardNumber, setCardNumber] = useState('')
  const [expiry, setExpiry] = useState('')
  const [cvc, setCvc] = useState('')
  const [touched, setTouched] = useState(false)

  const digits = cardNumber.replace(/\D/g, '')
  const errors = {
    cardName: cardName.trim().length < 2 ? 'Enter the name on the card' : null,
    cardNumber:
      digits.length !== 16 ? 'Card number must be 16 digits' : !passesLuhnCheck(digits) ? "That card number doesn't look right" : null,
    expiry: validateExpiry(expiry),
    cvc: !/^\d{3,4}$/.test(cvc) ? 'Enter a valid CVC' : null,
  }
  const isValid = !errors.cardName && !errors.cardNumber && !errors.expiry && !errors.cvc

  const payMutation = useMutation({
    mutationFn: async () => {
      // Simulated processing delay -- stands in for a real payment call.
      await new Promise((resolve) => setTimeout(resolve, 900))
      return api.patch('/businesses/me/plan', { plan: plan.key })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plan'] })
      onClose()
    },
  })

  const handleSubmit = () => {
    setTouched(true)
    if (isValid) payMutation.mutate()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Upgrade to ${plan.name}`}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Upgrade to {plan.name}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 text-slate-400" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3">
            <span className="text-base text-slate-600">{plan.name} plan</span>
            <span className="text-lg font-bold text-slate-900">{format(plan.price_usd)}/mo</span>
          </div>

          <Input
            label="Name on card"
            placeholder="Jane Doe"
            value={cardName}
            onChange={(e) => setCardName(e.target.value)}
            error={touched ? errors.cardName ?? undefined : undefined}
          />

          <Input
            label="Card number"
            placeholder="4242 4242 4242 4242"
            inputMode="numeric"
            value={cardNumber}
            onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
            error={touched ? errors.cardNumber ?? undefined : undefined}
          />

          <div className="flex gap-3">
            <Input
              label="Expiry"
              placeholder="MM/YY"
              inputMode="numeric"
              value={expiry}
              onChange={(e) => setExpiry(formatExpiry(e.target.value))}
              error={touched ? errors.expiry ?? undefined : undefined}
              className="flex-1"
            />
            <Input
              label="CVC"
              placeholder="123"
              inputMode="numeric"
              value={cvc}
              onChange={(e) => setCvc(e.target.value.replace(/\D/g, '').slice(0, 4))}
              error={touched ? errors.cvc ?? undefined : undefined}
              className="flex-1"
            />
          </div>

          <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
            <Lock size={14} className="mt-0.5 flex-shrink-0" />
            <span>
              No payment processor is connected yet, so no real charge is made and card details are never sent or
              stored anywhere. This switches your plan for demo purposes only.
            </span>
          </div>

          {payMutation.isError && (
            <p className="text-sm text-red-600">Couldn't complete the upgrade. Please try again.</p>
          )}

          <Button className="w-full justify-center" loading={payMutation.isPending} onClick={handleSubmit}>
            <CreditCard size={16} className="mr-2" />
            Pay {format(plan.price_usd)}/mo and upgrade
          </Button>
        </div>
      </div>
    </div>
  )
}
