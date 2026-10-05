import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { MessageSquare, Users, TrendingUp, Code, Lock } from 'lucide-react'
import { usePlan } from '../../shared/hooks/usePlan'
import { UsageMeter } from '../../shared/components/UsageMeter'
import { TestChatbotCard } from '../components/TestChatbotCard'
import { useT, type MessageKey } from '../../shared/i18n'

// Intent codes come from the API (rag/pipeline.py _detect_intent); only the labels are translated.
const INTENT_LABELS: Record<string, MessageKey> = {
  faq: 'overview.intents.faq',
  lead: 'overview.intents.lead',
  booking: 'overview.intents.booking',
  product_inquiry: 'overview.intents.product_inquiry',
  support: 'overview.intents.support',
}

interface Summary {
  conversation_count: number
  lead_count: number
  message_count: number
  analytics_tier: 'basic' | 'standard' | 'advanced'
  top_questions: { question: string; count: number }[]
  intent_breakdown: Record<string, number>
}

interface Business {
  id: string
  name: string
  slug: string
}

export function DashboardPage() {
  const { t, formatNumber } = useT()
  const { data: summary } = useQuery<Summary>({
    queryKey: ['analytics'],
    queryFn: () => api.get('/analytics/summary').then((r) => r.data),
  })
  const { data: plan } = usePlan()
  const { data: business } = useQuery<Business>({
    queryKey: ['business'],
    queryFn: () => api.get('/businesses/me').then((r) => r.data),
  })

  const embedScript = business
    ? `<script src="${window.location.origin}/widget.js" data-business="${business.id}"></script>`
    : ''

  const count = (n: number | undefined) => (n === undefined ? '—' : formatNumber(n))
  const stats = [
    { label: t('overview.stats.conversations'), value: count(summary?.conversation_count), icon: MessageSquare, bg: 'bg-blue-100', fg: 'text-blue-600' },
    { label: t('overview.stats.leads'), value: count(summary?.lead_count), icon: Users, bg: 'bg-emerald-100', fg: 'text-emerald-600' },
    { label: t('overview.stats.messages'), value: count(summary?.message_count), icon: TrendingUp, bg: 'bg-violet-100', fg: 'text-violet-600' },
  ]

  return (
    <div className="space-y-6">
      <div className="brand-gradient rounded-2xl p-6 shadow-sm shadow-brand-200 sm:p-8">
        <h1 className="text-4xl font-bold text-white">
          {business ? business.name : t('overview.fallbackTitle')}
        </h1>
        <p className="text-base text-brand-50 mt-1">{t('overview.welcome')}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map(({ label, value, icon: Icon, bg, fg }) => (
          <Card key={label}>
            <div className="flex items-center gap-4">
              <div className={`grid h-12 w-12 flex-shrink-0 place-items-center rounded-xl ${bg}`}>
                <Icon className={fg} size={22} />
              </div>
              <div>
                <p className="text-3xl font-bold text-slate-900">{value}</p>
                <p className="text-base text-slate-500">{label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* QA 2026-10-02 (E4): usage against the plan, where the owner looks first. */}
      {plan && (
        <Card>
          <div className="flex flex-wrap items-center gap-4">
            <div className="min-w-[14rem] flex-1">
              <UsageMeter
                label={t('overview.usageLabel', { plan: plan.plan_name })}
                used={plan.usage.conversations_this_month}
                limit={plan.limits.max_conversations_per_month}
              />
            </div>
            <Link to="/dashboard/plan" className="text-sm font-semibold text-brand-600 hover:underline">
              {t('overview.planLink')}
            </Link>
          </div>
        </Card>
      )}

      <TestChatbotCard />

      {summary?.analytics_tier === 'basic' && (
        <Card title={t('overview.topQuestions')}>
          <div className="flex items-center gap-3 text-base text-slate-500">
            <Lock size={16} className="flex-shrink-0" />
            <span className="flex-1">{t('overview.topQuestionsLocked')}</span>
            <Link to="/dashboard/plan" className="font-semibold text-brand-600 underline">{t('overview.upgrade')}</Link>
          </div>
        </Card>
      )}

      {summary && summary.top_questions.length > 0 && (
        <Card title={t('overview.topQuestions')}>
          <ul className="space-y-2">
            {summary.top_questions.map((q, i) => (
              <li key={i} className="flex items-center justify-between gap-4 text-base">
                <span className="text-slate-700 flex-1">{q.question}</span>
                <span
                  className={
                    i === 0
                      ? 'brand-gradient flex-shrink-0 rounded-full px-2.5 py-1 text-sm font-bold text-white shadow-sm shadow-brand-200'
                      : 'flex-shrink-0 rounded-full bg-violet-100 px-2.5 py-1 text-sm font-bold text-violet-700'
                  }
                >
                  {t('overview.chats', { count: q.count })}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {summary?.analytics_tier === 'advanced' && Object.keys(summary.intent_breakdown).length > 0 && (
        <Card title={t('overview.byIntent')}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(summary.intent_breakdown).map(([intent, count]) => (
              <div key={intent} className="rounded-xl bg-slate-50 p-3 text-center">
                <p className="text-2xl font-bold text-slate-900">{formatNumber(count)}</p>
                <p className="text-sm text-slate-500">
                  {INTENT_LABELS[intent] ? t(INTENT_LABELS[intent]) : intent.replace('_', ' ')} ·{' '}
                  {t('overview.intentConversations', { count })}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title={t('overview.embed.title')}>
        <p className="text-base text-slate-600 mb-3">
          {t('overview.embed.introBefore')}
          <code className="bg-slate-100 px-1 rounded">&lt;/body&gt;</code>
          {t('overview.embed.introAfter')}
        </p>
        <div className="flex items-start gap-3 bg-slate-50 rounded-lg p-3 border border-slate-200">
          <Code size={18} className="text-slate-400 mt-0.5 flex-shrink-0" />
          <code className="text-sm text-slate-700 break-all">{embedScript}</code>
        </div>
        <button
          onClick={() => navigator.clipboard.writeText(embedScript)}
          className="mt-3 text-sm text-brand-600 hover:underline"
        >
          {t('overview.embed.copy')}
        </button>
        {/* GDPR Phase 5: the business is the controller for its visitors' data. */}
        <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
          <p className="font-medium text-slate-700">{t('overview.embed.privacyTitle')}</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            <li>
              {t('overview.embed.cookiesBefore')}
              <code className="bg-white px-1 rounded">mielikkix_session</code>
              {t('overview.embed.cookiesMiddle')}
              <code className="bg-white px-1 rounded">mielikkix_chat_history</code>
              {t('overview.embed.cookiesAfter')}
            </li>
            <li>{t('overview.embed.aiNotice')}</li>
            <li>
              {t('overview.embed.settingsBefore')}
              <Link to="/dashboard/settings?tab=advanced" className="text-brand-600 hover:underline">{t('overview.embed.settingsLink')}</Link>
              {t('overview.embed.settingsAfter')}
            </li>
          </ul>
        </div>
      </Card>
    </div>
  )
}
