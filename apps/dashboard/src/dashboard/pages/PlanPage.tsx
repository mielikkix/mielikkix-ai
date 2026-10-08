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
import { usePlan, usePlanCatalog, PlanCatalogEntry } from '../../shared/hooks/usePlan'
import { CurrencySwitcher } from '../components/CurrencySwitcher'
import { useCurrency } from '../../shared/hooks/useCurrency'
import { t as translateNow, useT, type MessageKey } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

// The discontinued Business-plan API add-on -- only shown to a business that already has it
// (it can be cancelled, not newly enabled; API access is sold on Growth, see plans.py).
const API_ADDON_USD = 12

// max_languages: null means no numeric cap, but the widget only ever offers the curated
// codes in AVAILABLE_LANGUAGES (dashboard/pages/settings/types.ts) -- keep this count in
// sync with that list so plan copy doesn't promise more languages than a business can pick.
const SUPPORTED_LANGUAGE_COUNT = 10

// WhatsApp/Instagram are real plan features but have no backend integration
// built yet (see NOT_YET_IMPLEMENTED_FEATURES server-side) -- their lines say
// "(coming soon)" so the pricing cards don't imply they're usable today.
const ANALYTICS_LABELS: Record<PlanCatalogEntry['features']['analytics_tier'], MessageKey> = {
  basic: 'plan.features.analyticsBasic',
  standard: 'plan.features.analyticsStandard',
  advanced: 'plan.features.analyticsAdvanced',
}

// The catalog's taglines come from the API in English; known plans use the translated copy.
function planTagline(entry: PlanCatalogEntry): string {
  const keys: Record<string, MessageKey> = {
    free: 'plan.taglines.free',
    basic: 'plan.taglines.basic',
    business: 'plan.taglines.business',
    growth: 'plan.taglines.growth',
  }
  return keys[entry.key] ? translateNow(keys[entry.key]) : entry.tagline
}

// The label the API gives a site it found from widget traffic
// (apps/api/app/services/website_service.py, WIDGET_DETECTED_LABEL). Stored as
// English text, so it is translated here (QA 2026-10-08, A-06).
const WIDGET_DETECTED_LABEL = 'Detected from your chat widget'

interface Website {
  id: string
  domain: string
  label: string | null
}

function WebsitesCard() {
  const qc = useQueryClient()
  const { t } = useT()
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
    <Card title={t('plan.websites.title')}>
      <div className="space-y-3">
        {websites.map((w) => (
          <div key={w.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2">
            <div>
              <p className="text-base font-medium text-slate-800">{w.domain}</p>
              {w.label && (
                <p className="text-sm text-slate-400">
                  {w.label === WIDGET_DETECTED_LABEL ? t('plan.websites.detectedFromWidget') : w.label}
                </p>
              )}
            </div>
            <button
              onClick={() => deleteMut.mutate(w.id)}
              className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
              aria-label={t('plan.websites.remove', { domain: w.domain })}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {websites.length === 0 && <p className="text-base text-slate-400">{t('plan.websites.empty')}</p>}

        <div className="flex flex-wrap gap-2 pt-1">
          <Input
            placeholder={t('plan.websites.domainPlaceholder')}
            aria-label={t('plan.websites.domainLabel')}
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={atLimit}
            className="flex-1 min-w-[10rem]"
          />
          <Input
            placeholder={t('plan.websites.labelPlaceholder')}
            aria-label={t('plan.websites.labelLabel')}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={atLimit}
            className="flex-1 min-w-[10rem]"
          />
          <Button size="sm" disabled={!domain.trim() || atLimit} loading={addMut.isPending} onClick={() => addMut.mutate()}>
            {t('plan.websites.add')}
          </Button>
        </div>
        {atLimit && (
          <p className="text-sm text-brand-600">{t('plan.websites.atLimit')}</p>
        )}
        {addMut.isError && (
          <p role="alert" className="text-sm text-red-600">{apiErrorMessage(addMut.error, 'plan.websites.addFailed')}</p>
        )}
      </div>
    </Card>
  )
}

function ApiAccessCard() {
  const qc = useQueryClient()
  const { t } = useT()
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
    <Card title={t('plan.api.title')}>
      {/* QA 2026-10-02 (M2): the website sells API access on Growth only -- no Business add-on upsell. */}
      {!hasAccess && <PlanGate feature="api_access"><span /></PlanGate>}

      {hasAccess && (
        <div className="space-y-3">
          {isBusinessPlan && plan.api_access_addon && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-medium text-emerald-600">{t('plan.api.addonActive', { price: API_ADDON_USD })}</p>
              <Button size="sm" variant="secondary" loading={addonMut.isPending} onClick={() => addonMut.mutate(false)}>
                {t('plan.api.cancelAddon')}
              </Button>
            </div>
          )}
          {keyInfo?.api_key ? (
            <div className="flex flex-wrap items-center gap-2">
              <code className="flex-1 min-w-[12rem] truncate rounded-lg bg-slate-100 px-3 py-2 text-sm">{keyInfo.api_key}</code>
              <Button size="sm" variant="secondary" onClick={() => navigator.clipboard.writeText(keyInfo.api_key!)}>
                {t('plan.api.copy')}
              </Button>
              <Button size="sm" variant="danger" loading={revokeMut.isPending} onClick={() => revokeMut.mutate()}>
                {t('plan.api.revoke')}
              </Button>
            </div>
          ) : (
            <Button size="sm" loading={genMut.isPending} onClick={() => genMut.mutate()}>
              {t('plan.api.generate')}
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

function planFeatureLines(entry: PlanCatalogEntry, t: ReturnType<typeof useT>['t']): string[] {
  const { limits, features } = entry
  const lines: string[] = [
    limits.max_websites === null
      ? t('plan.features.unlimitedWebsites')
      : t('plan.features.websites', { count: limits.max_websites }),
    limits.max_conversations_per_month === null
      ? t('plan.features.unlimitedConversations')
      : t('plan.features.conversations', { count: limits.max_conversations_per_month }),
    t('plan.features.knowledgeBase'),
    limits.max_document_uploads === null
      ? t('plan.features.unlimitedDocuments')
      : t('plan.features.documents', { count: limits.max_document_uploads }),
    t('plan.features.leadCapture'),
    t(ANALYTICS_LABELS[features.analytics_tier] ?? 'plan.features.analyticsBasic'),
    limits.max_products === null
      ? t('plan.features.unlimitedProducts')
      : t('plan.features.products', { count: limits.max_products }),
    limits.conversation_history_days === null
      ? t('plan.features.historyRetention')
      : limits.conversation_history_days >= 365
        ? t('plan.features.history12')
        : t('plan.features.historyDays', { count: limits.conversation_history_days }),
    features.whatsapp_notifications ? t('plan.features.emailWhatsapp') : t('plan.features.emailNotifications'),
  ]
  if (features.instagram_integration) lines.push(t('plan.features.instagram'))
  if (limits.max_languages === null) lines.push(t('plan.features.languages', { count: SUPPORTED_LANGUAGE_COUNT }))
  else if (limits.max_languages > 1) lines.push(t('plan.features.languages', { count: limits.max_languages }))
  if (features.multi_currency) lines.push(t('plan.features.multiCurrency'))
  if (features.custom_branding) lines.push(t('plan.features.customBranding'))
  if (features.api_access) lines.push(t('plan.features.apiAccess'))
  if (features.priority_support) lines.push(t('plan.features.prioritySupport'))
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
  const { t, formatNok } = useT()
  const { data: status } = usePlan()
  const { data: catalog } = usePlanCatalog()
  const [checkoutPlan, setCheckoutPlan] = useState<PlanCatalogEntry | null>(null)
  const [comingSoonPlan, setComingSoonPlan] = useState<PlanCatalogEntry | null>(null)
  const { currency, setCurrency, format, converted } = useCurrency()

  // Free needs no payment step; paid plans go through checkout first.
  const chooseMutation = useMutation({
    mutationFn: (plan: string) => api.patch('/businesses/me/plan', { plan }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plan'] }),
  })

  const handleChoosePlan = (entry: PlanCatalogEntry) => {
    if (entry.price_nok === 0) {
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
          <h1 className="text-4xl font-bold text-slate-900">{t('plan.title')}</h1>
          <p className="text-base text-slate-500 mt-1">
            {t('plan.currentBefore')}
            <span className="font-semibold text-slate-700">{status?.plan_name ?? '—'}</span>
            {t('plan.currentAfter')}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <CurrencySwitcher currency={currency} onChange={setCurrency} />
          <p className="text-xs text-slate-500">{t('plan.pricesNote')}</p>
        </div>
      </div>

      {status && (
        <Card title={t('plan.usageTitle')}>
          <div className="grid gap-4 sm:grid-cols-2">
            <UsageMeter label={t('plan.usage.websites')} used={status.usage.websites} limit={status.limits.max_websites} />
            <UsageMeter
              label={t('plan.usage.conversations')}
              used={status.usage.conversations_this_month}
              limit={status.limits.max_conversations_per_month}
            />
            <UsageMeter label={t('plan.usage.documents')} used={status.usage.documents} limit={status.limits.max_document_uploads} />
            <UsageMeter label={t('plan.usage.products')} used={status.usage.products} limit={status.limits.max_products} />
          </div>
        </Card>
      )}

      <WebsitesCard />
      <ApiAccessCard />

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
                  <Star size={12} /> {t('plan.mostPopular')}
                </span>
              )}
              <h3 className={clsx('text-xl font-bold', isPopular ? 'text-white' : 'text-slate-900')}>{entry.name}</h3>
              <p className={clsx('text-sm mt-1', isPopular ? 'text-brand-50' : 'text-slate-500')}>{planTagline(entry)}</p>
              <p className="mt-4">
                <span className={clsx('text-3xl font-bold', isPopular ? 'text-white' : 'text-slate-900')}>
                  {formatNok(entry.price_nok)}
                </span>
                <span className={clsx('text-sm', isPopular ? 'text-brand-50' : 'text-slate-500')}>
                  {entry.price_nok === 0 ? t('plan.forever') : t('plan.perMonthExclVat')}
                </span>
              </p>
              {/* NOK is the real price (QA 2026-10-02, M1); EUR/USD is only a conversion. */}
              {converted && entry.price_nok > 0 && (
                <p className={clsx('text-xs', isPopular ? 'text-brand-50' : 'text-slate-500')}>
                  {t('plan.approxToday', { price: format(entry.price_nok) })}
                </p>
              )}

              <Button
                className="mt-4 w-full justify-center"
                variant={isPopular ? 'secondary' : isCurrent ? 'secondary' : 'primary'}
                disabled={isCurrent}
                loading={chooseMutation.isPending && chooseMutation.variables === entry.key}
                onClick={() => handleChoosePlan(entry)}
              >
                {isCurrent ? t('plan.currentPlan') : t('plan.choose', { plan: entry.name })}
              </Button>

              <ul className="mt-5 space-y-2 flex-1">
                {planFeatureLines(entry, t).map((line) => (
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
        <p role="alert" className="text-base text-red-600">{apiErrorMessage(chooseMutation.error, 'plan.switchFailed')}</p>
      )}

      {checkoutPlan && <CheckoutModal plan={checkoutPlan} format={format} onClose={() => setCheckoutPlan(null)} />}
      {comingSoonPlan && <PaymentComingSoonModal plan={comingSoonPlan} onClose={() => setComingSoonPlan(null)} />}
    </div>
  )
}
