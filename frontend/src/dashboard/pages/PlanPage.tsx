import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Star, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { UsageMeter } from '../../shared/components/UsageMeter'
import { PlanGate } from '../../shared/components/PlanGate'
import { CheckoutModal } from '../components/CheckoutModal'
import { PaymentComingSoonModal } from '../components/PaymentComingSoonModal'
import { CurrencySwitcher } from '../components/CurrencySwitcher'
import { usePlan, usePlanCatalog, PlanCatalogEntry } from '../../shared/hooks/usePlan'
import { useCurrency } from '../../shared/hooks/useCurrency'

// The API access add-on price isn't part of the plan catalog response (it's a flat backend
// constant, see app/api/businesses.py's set_api_access_addon docstring) -- kept in sync here.
const API_ADDON_USD = 12

// max_languages: null means no numeric cap, but the widget only ever offers the curated
// codes in AVAILABLE_LANGUAGES (SettingsPage.tsx) -- keep this count in sync with that list
// so plan copy doesn't promise more languages than a business can actually pick.
const SUPPORTED_LANGUAGE_COUNT = 10

// WhatsApp/Instagram are real plan features but have no backend integration
// built yet (see NOT_YET_IMPLEMENTED_FEATURES server-side) -- marked here so
// the pricing cards don't imply they're usable today.
const COMING_SOON_SUFFIX = ' (coming soon)'

const FEATURE_LABELS: Record<string, (f: PlanCatalogEntry['features']) => string | null> = {
  knowledge_base: () => 'Knowledge base',
  lead_capture: () => 'Lead capture',
  analytics_tier: (f) =>
    f.analytics_tier === 'advanced' ? 'Advanced analytics' : f.analytics_tier === 'standard' ? 'Standard analytics' : 'Basic analytics',
  email_notifications: (f) =>
    f.whatsapp_notifications ? `Email + WhatsApp notifications${COMING_SOON_SUFFIX}` : 'Email notifications',
  instagram_integration: (f) => (f.instagram_integration ? `Instagram integration${COMING_SOON_SUFFIX}` : null),
  multi_currency: (f) => (f.multi_currency ? 'Multi-currency' : null),
  custom_branding: (f) => (f.custom_branding ? 'Custom branding' : null),
  priority_support: (f) => (f.priority_support ? 'Priority support' : null),
}

function apiAccessLabel(features: PlanCatalogEntry['features'], format: (usd: number) => string): string | null {
  if (features.api_access) return 'API access included'
  if (features.api_access_addon_available) return `API access (+${format(API_ADDON_USD)}/mo add-on)`
  return null
}

interface Website {
  id: string
  domain: string
  label: string | null
}

function WebsitesCard() {
  const qc = useQueryClient()
  const { data: plan } = usePlan()
  const { data: websites = [] } = useQuery<Website[]>({
    queryKey: ['websites'],
    queryFn: () => api.get('/websites').then((r) => r.data),
  })
  const [domain, setDomain] = useState('')
  const [label, setLabel] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['websites'] })
    qc.invalidateQueries({ queryKey: ['plan'] })
  }

  const addMut = useMutation({
    mutationFn: () => api.post('/websites', { domain, label: label.trim() || undefined }),
    onSuccess: () => { invalidate(); setDomain(''); setLabel('') },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/websites/${id}`),
    onSuccess: invalidate,
  })

  const atLimit = !!plan && plan.limits.max_websites !== null && websites.length >= plan.limits.max_websites

  return (
    <Card title="Your websites">
      <div className="space-y-3">
        {websites.map((w) => (
          <div key={w.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2">
            <div>
              <p className="text-base font-medium text-slate-800">{w.domain}</p>
              {w.label && <p className="text-sm text-slate-400">{w.label}</p>}
            </div>
            <button
              onClick={() => deleteMut.mutate(w.id)}
              className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
              aria-label={`Remove ${w.domain}`}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {websites.length === 0 && <p className="text-base text-slate-400">No websites registered yet.</p>}

        <div className="flex flex-wrap gap-2 pt-1">
          <Input
            placeholder="yourdomain.com"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={atLimit}
            className="flex-1 min-w-[10rem]"
          />
          <Input
            placeholder="Label (optional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={atLimit}
            className="flex-1 min-w-[10rem]"
          />
          <Button size="sm" disabled={!domain.trim() || atLimit} loading={addMut.isPending} onClick={() => addMut.mutate()}>
            Add
          </Button>
        </div>
        {atLimit && (
          <p className="text-sm text-brand-600">
            You've reached your plan's website limit. Upgrade below to add more.
          </p>
        )}
        {addMut.isError && (
          <p className="text-sm text-red-600">
            {(addMut.error as any)?.response?.data?.detail ?? 'Could not add that website.'}
          </p>
        )}
      </div>
    </Card>
  )
}

function ApiAccessCard({ format }: { format: (usd: number) => string }) {
  const qc = useQueryClient()
  const { data: plan } = usePlan()
  const { data: keyInfo } = useQuery<{ api_key: string | null }>({
    queryKey: ['api-key'],
    queryFn: () => api.get('/businesses/me/api-key').then((r) => r.data),
  })

  const addonMut = useMutation({
    mutationFn: (enabled: boolean) => api.patch('/businesses/me/plan/api-access-addon', { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plan'] }),
  })
  const genMut = useMutation({
    mutationFn: () => api.post('/businesses/me/api-key'),
    onSuccess: (r) => qc.setQueryData(['api-key'], r.data),
  })
  const revokeMut = useMutation({
    mutationFn: () => api.delete('/businesses/me/api-key'),
    onSuccess: (r) => qc.setQueryData(['api-key'], r.data),
  })

  if (!plan) return null

  const isBusinessPlan = plan.plan === 'business'
  const hasAccess = plan.features.api_access

  return (
    <Card title="API access">
      {!hasAccess && !isBusinessPlan && <PlanGate feature="api_access"><span /></PlanGate>}

      {isBusinessPlan && !plan.api_access_addon && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-base text-slate-600">Add API access to your Business plan for +{format(API_ADDON_USD)}/mo.</p>
          <Button size="sm" loading={addonMut.isPending} onClick={() => addonMut.mutate(true)}>
            Enable add-on
          </Button>
        </div>
      )}

      {hasAccess && (
        <div className="space-y-3">
          {isBusinessPlan && plan.api_access_addon && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-medium text-emerald-600">API access add-on active (+{format(API_ADDON_USD)}/mo)</p>
              <Button size="sm" variant="secondary" loading={addonMut.isPending} onClick={() => addonMut.mutate(false)}>
                Cancel add-on
              </Button>
            </div>
          )}
          {keyInfo?.api_key ? (
            <div className="flex flex-wrap items-center gap-2">
              <code className="flex-1 min-w-[12rem] truncate rounded-lg bg-slate-100 px-3 py-2 text-sm">{keyInfo.api_key}</code>
              <Button size="sm" variant="secondary" onClick={() => navigator.clipboard.writeText(keyInfo.api_key!)}>
                Copy
              </Button>
              <Button size="sm" variant="danger" loading={revokeMut.isPending} onClick={() => revokeMut.mutate()}>
                Revoke
              </Button>
            </div>
          ) : (
            <Button size="sm" loading={genMut.isPending} onClick={() => genMut.mutate()}>
              Generate API key
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

function planFeatureLines(entry: PlanCatalogEntry, format: (usd: number) => string): string[] {
  const { limits, features } = entry
  const lines: string[] = [
    `${limits.max_websites ?? 'Unlimited'} website${limits.max_websites === 1 ? '' : 's'}`,
    `${limits.max_conversations_per_month?.toLocaleString() ?? 'Unlimited'} AI conversations/mo`,
    'Knowledge base',
    limits.max_document_uploads === null ? 'Unlimited document uploads' : `${limits.max_document_uploads} document uploads`,
    'Lead capture',
    FEATURE_LABELS.analytics_tier(features)!,
    limits.max_products === null ? 'Unlimited products' : `${limits.max_products} products in catalog`,
    limits.conversation_history_days === null
      ? 'Unlimited conversation history'
      : `${limits.conversation_history_days}-day conversation history`,
    FEATURE_LABELS.email_notifications(features)!,
  ]
  if (features.instagram_integration) lines.push('Instagram integration')
  if (limits.max_languages === null) lines.push(`Up to ${SUPPORTED_LANGUAGE_COUNT} languages`)
  else if (limits.max_languages > 1) lines.push(`${limits.max_languages} languages`)
  if (features.multi_currency) lines.push('Multi-currency')
  if (features.custom_branding) lines.push('Custom branding')
  const apiLine = apiAccessLabel(features, format)
  if (apiLine) lines.push(apiLine)
  if (features.priority_support) lines.push('Priority support')
  return lines
}

// No payment processor is connected yet (see CheckoutModal.tsx), so paid
// plans aren't actually purchasable. Flip to false to bring back the fake
// checkout flow for local testing/dev; leave true everywhere else
// (including production) so business owners see "coming soon" instead of
// "paying" for real.
const PAYMENT_COMING_SOON = true

export function PlanPage() {
  const qc = useQueryClient()
  const { data: status } = usePlan()
  const { data: catalog } = usePlanCatalog()
  const [checkoutPlan, setCheckoutPlan] = useState<PlanCatalogEntry | null>(null)
  const [comingSoonPlan, setComingSoonPlan] = useState<PlanCatalogEntry | null>(null)
  const { currency, setCurrency, format } = useCurrency()

  // Free needs no payment step; paid plans go through checkout first.
  const chooseMutation = useMutation({
    mutationFn: (plan: string) => api.patch('/businesses/me/plan', { plan }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plan'] }),
  })

  const handleChoosePlan = (entry: PlanCatalogEntry) => {
    if (entry.price_usd === 0) {
      chooseMutation.mutate(entry.key)
    } else if (PAYMENT_COMING_SOON) {
      setComingSoonPlan(entry)
    } else {
      setCheckoutPlan(entry)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">Plan &amp; Billing</h1>
          <p className="text-base text-slate-500 mt-1">
            You're currently on the <span className="font-semibold text-slate-700">{status?.plan_name ?? '—'}</span> plan.
          </p>
        </div>
        <CurrencySwitcher currency={currency} onChange={setCurrency} />
      </div>

      {status && (
        <Card title="Current usage">
          <div className="grid gap-4 sm:grid-cols-2">
            <UsageMeter label="Websites" used={status.usage.websites} limit={status.limits.max_websites} />
            <UsageMeter
              label="AI conversations this month"
              used={status.usage.conversations_this_month}
              limit={status.limits.max_conversations_per_month}
            />
            <UsageMeter label="Documents" used={status.usage.documents} limit={status.limits.max_document_uploads} />
            <UsageMeter label="Products" used={status.usage.products} limit={status.limits.max_products} />
          </div>
        </Card>
      )}

      <WebsitesCard />
      <ApiAccessCard format={format} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {catalog?.map((entry) => {
          const isCurrent = status?.plan === entry.key
          const isPopular = entry.key === 'business'
          return (
            <div
              key={entry.key}
              className={clsx(
                'flex flex-col rounded-2xl border p-6',
                isPopular ? 'brand-gradient text-white shadow-sm shadow-brand-200' : 'bg-white border-slate-300'
              )}
            >
              {isPopular && (
                <span className="mb-2 inline-flex w-fit items-center gap-1 rounded-full bg-white/20 px-2.5 py-1 text-sm font-semibold">
                  <Star size={12} /> Most Popular
                </span>
              )}
              <h3 className={clsx('text-xl font-bold', isPopular ? 'text-white' : 'text-slate-900')}>{entry.name}</h3>
              <p className={clsx('text-sm mt-1', isPopular ? 'text-brand-50' : 'text-slate-500')}>{entry.tagline}</p>
              <p className="mt-4">
                <span className={clsx('text-3xl font-bold', isPopular ? 'text-white' : 'text-slate-900')}>
                  {format(entry.price_usd)}
                </span>
                <span className={clsx('text-sm', isPopular ? 'text-brand-50' : 'text-slate-500')}>
                  {entry.price_usd === 0 ? ' forever' : '/mo'}
                </span>
              </p>

              <Button
                className="mt-4 w-full justify-center"
                variant={isPopular ? 'secondary' : isCurrent ? 'secondary' : 'primary'}
                disabled={isCurrent}
                loading={chooseMutation.isPending && chooseMutation.variables === entry.key}
                onClick={() => handleChoosePlan(entry)}
              >
                {isCurrent ? 'Current plan' : `Choose ${entry.name}`}
              </Button>

              <ul className="mt-5 space-y-2 flex-1">
                {planFeatureLines(entry, format).map((line) => (
                  <li
                    key={line}
                    className={clsx('flex items-start gap-2 text-sm', isPopular ? 'text-white' : 'text-slate-600')}
                  >
                    <Check size={15} className={clsx('mt-0.5 flex-shrink-0', isPopular ? 'text-white' : 'text-emerald-600')} />
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>

      {chooseMutation.isError && (
        <p className="text-base text-red-600">Couldn't switch plans. Please try again.</p>
      )}

      {checkoutPlan && <CheckoutModal plan={checkoutPlan} format={format} onClose={() => setCheckoutPlan(null)} />}
      {comingSoonPlan && <PaymentComingSoonModal plan={comingSoonPlan} onClose={() => setComingSoonPlan(null)} />}
    </div>
  )
}
