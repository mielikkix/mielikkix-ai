import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, Users, RefreshCw, Plus, Send, Clock, FlaskConical, BarChart3 } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { AgentGate } from '../../shared/components/AgentGate'
import { useAgentAccess } from '../../shared/hooks/usePlan'
import { useT, type MessageKey } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

interface MailchimpStatus {
  connected: boolean
  configured: boolean
  account_name?: string | null
  login_email?: string | null
  audience_id?: string | null
  audience_name?: string | null
  connected_at?: string | null
}

interface MailchimpAudience {
  id: string
  name: string
  member_count: number
}

interface Campaign {
  id: string
  mailchimp_audience_id: string | null
  mailchimp_audience_name: string | null
  mailchimp_campaign_id: string | null
  subject: string | null
  from_name: string | null
  from_email: string | null
  reply_to: string | null
  body_html: string | null
  status: string
  scheduled_at: string | null
  sent_at: string | null
  created_at: string | null
  updated_at: string | null
}

interface CampaignReport {
  emails_sent: number
  opens_total: number
  unique_opens: number
  open_rate: number
  click_rate: number
  unsubscribed: number
  hard_bounces: number
  soft_bounces: number
}

// Only Mailchimp exists today -- see app/integrations/email_marketing_providers/
// __init__.py's PROVIDER_NAMES for the roadmapped ("resend") but not-yet-built
// second provider. This page is intentionally Mailchimp-only for Phase 1;
// a provider picker isn't needed until a second provider actually exists.
//
// Mailchimp is the system of record for a campaign itself -- it drafts,
// sends, and reports on it natively via its own Campaigns API (see
// app/services/campaign_service.py). This page only manages the LOCAL
// draft (subject/from_name/reply_to/body) before send/schedule/test, and
// reads Mailchimp's own live status/report back -- it never tracks
// individual recipients itself.

function AudiencePicker({ selectedId, onSelected }: { selectedId?: string | null; onSelected: () => void }) {
  const qc = useQueryClient()
  const { t } = useT()
  const {
    data: audiences,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<MailchimpAudience[]>({
    queryKey: ['mailchimp-audiences'],
    queryFn: () => api.get('/businesses/me/mailchimp/audiences').then((r) => r.data),
  })

  const selectMut = useMutation({
    mutationFn: (audience: MailchimpAudience) =>
      api.post('/businesses/me/mailchimp/select-audience', { audience_id: audience.id, name: audience.name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mailchimp-status'] })
      onSelected()
    },
  })

  if (isLoading) {
    return <p className="text-sm text-slate-500">{t('email.audiences.loading')}</p>
  }

  if (isError) {
    return (
      <div className="space-y-2">
        <p role="alert" className="text-sm font-medium text-red-600">{apiErrorMessage(error, 'email.audiences.loadFailed')}</p>
        <Button size="sm" variant="secondary" loading={isFetching} onClick={() => refetch()}>
          <RefreshCw size={14} className="mr-1" />
          {t('email.audiences.retry')}
        </Button>
      </div>
    )
  }

  if (!audiences || audiences.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-slate-500">{t('email.audiences.none')}</p>
        <Button size="sm" variant="secondary" loading={isFetching} onClick={() => refetch()}>
          <RefreshCw size={14} className="mr-1" />
          {t('email.audiences.refresh')}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {selectMut.isError && (
        <p role="alert" className="text-sm font-medium text-red-600">{apiErrorMessage(selectMut.error, 'email.audiences.selectFailed')}</p>
      )}
      {audiences.map((audience) => (
        <div
          key={audience.id}
          className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-3"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-900">{audience.name}</p>
            <p className="flex items-center gap-1 text-xs text-slate-500">
              <Users size={12} />
              {t('email.audiences.contacts', { count: audience.member_count })}
            </p>
          </div>
          <Button
            size="sm"
            variant={audience.id === selectedId ? 'secondary' : 'primary'}
            disabled={audience.id === selectedId}
            loading={selectMut.isPending && selectMut.variables?.id === audience.id}
            onClick={() => selectMut.mutate(audience)}
          >
            {audience.id === selectedId ? t('email.audiences.selected') : t('email.audiences.select')}
          </Button>
        </div>
      ))}
    </div>
  )
}

function MailchimpConnectionCard({ status, isLoading }: { status?: MailchimpStatus; isLoading: boolean }) {
  const qc = useQueryClient()
  const { t } = useT()
  const [searchParams, setSearchParams] = useSearchParams()
  const [banner, setBanner] = useState<'connected' | 'error' | null>(null)
  const [changingAudience, setChangingAudience] = useState(false)
  const [connecting, setConnecting] = useState(false)

  useEffect(() => {
    const value = searchParams.get('mailchimp')
    if (value === 'connected' || value === 'error') {
      setBanner(value)
      qc.invalidateQueries({ queryKey: ['mailchimp-status'] })
      const next = new URLSearchParams(searchParams)
      next.delete('mailchimp')
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const disconnectMut = useMutation({
    mutationFn: () => api.delete('/businesses/me/mailchimp'),
    onSuccess: () => {
      setBanner(null)
      setChangingAudience(false)
      qc.invalidateQueries({ queryKey: ['mailchimp-status'] })
    },
  })

  if (isLoading) return null

  if (!status?.configured) {
    return (
      <Card title="Mailchimp">
        {/* QA 2026-10-02 (D5): this read "isn't set up for this environment yet" -- developer wording. */}
        <p className="text-sm text-slate-500">
          <span className="mr-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700">{t('email.connection.soonBadge')}</span>
          {t('email.connection.soonText')}
        </p>
      </Card>
    )
  }

  if (!status.connected) {
    return (
      <Card title="Mailchimp">
        <div className="space-y-3">
          {banner === 'error' && <p role="alert" className="text-sm text-red-600">{t('email.connection.connectFailed')}</p>}
          <p className="text-sm text-slate-500">{t('email.connection.connectHelp')}</p>
          <Button
            size="sm"
            loading={connecting}
            onClick={() => {
              setConnecting(true)
              window.location.href = `${api.defaults.baseURL}/businesses/me/mailchimp/authorize`
            }}
          >
            <Mail size={14} className="mr-1" />
            {t('email.connection.connect')}
          </Button>
        </div>
      </Card>
    )
  }

  const showPicker = changingAudience || !status.audience_id

  return (
    <Card title="Mailchimp">
      <div className="space-y-3">
        {banner === 'connected' && <p role="status" className="text-sm text-emerald-600">{t('email.connection.connectedBanner')}</p>}
        <p className="text-sm text-slate-700">
          {t('email.connection.connected')}
          {status.account_name ? ` -- ${status.account_name}` : ''}
          {status.login_email ? ` (${status.login_email})` : ''}.
        </p>

        {status.audience_id && !showPicker && (
          <div className="rounded-xl bg-slate-50 px-4 py-3">
            <p className="text-sm font-medium text-slate-900">
              {t('email.connection.selectedAudience', { name: status.audience_name || status.audience_id || '' })}
            </p>
          </div>
        )}

        {!showPicker ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => setChangingAudience(true)}>
              {t('email.connection.changeAudience')}
            </Button>
            <Button size="sm" variant="danger" loading={disconnectMut.isPending} onClick={() => disconnectMut.mutate()}>
              {t('email.connection.disconnect')}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-500">{t('email.connection.chooseAudience')}</p>
            <AudiencePicker selectedId={status.audience_id} onSelected={() => setChangingAudience(false)} />
            <div className="flex flex-wrap gap-2">
              {status.audience_id && (
                <Button size="sm" variant="ghost" onClick={() => setChangingAudience(false)}>
                  {t('email.connection.cancel')}
                </Button>
              )}
              <Button size="sm" variant="danger" loading={disconnectMut.isPending} onClick={() => disconnectMut.mutate()}>
                {t('email.connection.disconnect')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

// Status values come from Mailchimp/the API; only the labels are translated.
const STATUS_LABEL: Record<string, MessageKey> = {
  draft: 'email.status.draft',
  approved: 'email.status.approved',
  save: 'email.status.approved',
  paused: 'email.status.paused',
  schedule: 'email.status.scheduled',
  sending: 'email.status.sending',
  sent: 'email.status.sent',
  canceled: 'email.status.canceled',
  canceling: 'email.status.canceling',
  archived: 'email.status.archived',
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  approved: 'bg-blue-100 text-blue-700',
  save: 'bg-blue-100 text-blue-700',
  paused: 'bg-amber-100 text-amber-700',
  schedule: 'bg-violet-100 text-violet-700',
  sending: 'bg-amber-100 text-amber-700',
  sent: 'bg-emerald-100 text-emerald-700',
  canceled: 'bg-red-100 text-red-700',
  canceling: 'bg-red-100 text-red-700',
  archived: 'bg-slate-100 text-slate-500',
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useT()
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[status] || 'bg-slate-100 text-slate-600'}`}>
      {STATUS_LABEL[status] ? t(STATUS_LABEL[status]) : status}
    </span>
  )
}

function CampaignReportPanel({ campaignId }: { campaignId: string }) {
  const { t, formatNumber } = useT()
  // Mailchimp reports rates as percentages (12.5 = 12.5 %).
  const pct = (value: number) => `${formatNumber(value, 1)} %`
  const { data: report, isLoading, isError, error } = useQuery<CampaignReport>({
    queryKey: ['campaign-report', campaignId],
    queryFn: () => api.get(`/businesses/me/campaigns/${campaignId}/report`).then((r) => r.data),
  })

  if (isLoading) return <p className="text-sm text-slate-500">{t('email.report.loading')}</p>
  if (isError) {
    return <p className="text-sm text-slate-500">{apiErrorMessage(error, 'email.report.notAvailable')}</p>
  }
  if (!report) return null

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        [t('email.report.sent'), formatNumber(report.emails_sent)],
        [t('email.report.opens'), pct(report.open_rate)],
        [t('email.report.clicks'), pct(report.click_rate)],
        [t('email.report.unsubscribed'), formatNumber(report.unsubscribed)],
        [t('email.report.uniqueOpens'), formatNumber(report.unique_opens)],
        [t('email.report.hardBounces'), formatNumber(report.hard_bounces)],
        [t('email.report.softBounces'), formatNumber(report.soft_bounces)],
      ].map(([label, value]) => (
        <div key={label} className="rounded-xl bg-slate-50 px-3 py-2">
          <p className="text-xs text-slate-500">{label}</p>
          <p className="text-lg font-semibold text-slate-900">{value}</p>
        </div>
      ))}
    </div>
  )
}

interface ComposerProps {
  campaign: Campaign | null
  mailchimpStatus?: MailchimpStatus
  onClose: () => void
}

function CampaignComposer({ campaign, mailchimpStatus, onClose }: ComposerProps) {
  const qc = useQueryClient()
  const { t } = useT()
  const isNew = campaign === null
  const [subject, setSubject] = useState(campaign?.subject || '')
  const [fromName, setFromName] = useState(campaign?.from_name || '')
  const [fromEmail, setFromEmail] = useState(campaign?.from_email || '')
  const [replyTo, setReplyTo] = useState(campaign?.reply_to || '')
  const [bodyHtml, setBodyHtml] = useState(campaign?.body_html || '')
  const [audienceId, setAudienceId] = useState(campaign?.mailchimp_audience_id || mailchimpStatus?.audience_id || '')
  const [audienceName, setAudienceName] = useState(campaign?.mailchimp_audience_name || mailchimpStatus?.audience_name || '')
  const [testEmails, setTestEmails] = useState('')
  const [confirmingSend, setConfirmingSend] = useState(false)
  const [scheduleAt, setScheduleAt] = useState('')
  const [savedId, setSavedId] = useState<string | null>(campaign?.id || null)
  const [showReport, setShowReport] = useState(false)

  // The connection's own audiences (same query AudiencePicker above uses)
  // -- reused here purely to let a campaign target a DIFFERENT audience
  // than the connection's current default, without reusing AudiencePicker
  // itself (that component's Select mutates the CONNECTION's own default
  // audience, which would be the wrong action for "pick this campaign's
  // audience").
  const { data: audiences } = useQuery<MailchimpAudience[]>({
    queryKey: ['mailchimp-audiences'],
    queryFn: () => api.get('/businesses/me/mailchimp/audiences').then((r) => r.data),
    enabled: isNew || campaign?.status === 'draft',
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['campaigns'] })
    qc.invalidateQueries({ queryKey: ['campaign-report', savedId] })
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const body = {
        subject: subject || null,
        from_name: fromName || null,
        from_email: fromEmail || null,
        reply_to: replyTo || null,
        body_html: bodyHtml || null,
        mailchimp_audience_id: audienceId || null,
        mailchimp_audience_name: audienceName || null,
      }
      return savedId
        ? api.patch<Campaign>(`/businesses/me/campaigns/${savedId}`, body)
        : api.post<Campaign>('/businesses/me/campaigns', body)
    },
    onSuccess: (res) => {
      setSavedId(res.data.id)
      invalidate()
    },
  })

  const approveMut = useMutation({
    mutationFn: () => api.post<Campaign>(`/businesses/me/campaigns/${savedId}/approve`),
    onSuccess: invalidate,
  })

  const testMut = useMutation({
    mutationFn: () =>
      api.post<Campaign>(`/businesses/me/campaigns/${savedId}/test`, {
        test_emails: testEmails.split(',').map((e) => e.trim()).filter(Boolean),
      }),
    onSuccess: invalidate,
  })

  const sendMut = useMutation({
    mutationFn: () => api.post<Campaign>(`/businesses/me/campaigns/${savedId}/send`),
    onSuccess: () => {
      setConfirmingSend(false)
      invalidate()
    },
  })

  const scheduleMut = useMutation({
    mutationFn: () =>
      api.post<Campaign>(`/businesses/me/campaigns/${savedId}/schedule`, {
        scheduled_at: new Date(scheduleAt).toISOString(),
      }),
    onSuccess: invalidate,
  })

  const status = campaign?.status || 'draft'
  const isDraft = status === 'draft'
  const isSendable = ['approved', 'save', 'paused'].includes(status)
  const hasReport = ['sending', 'sent'].includes(status)
  const anyError = saveMut.error || approveMut.error || testMut.error || sendMut.error || scheduleMut.error

  return (
    <Card
      title={
        isNew ? t('email.composer.newTitle') : t('email.composer.title', { subject: campaign?.subject || t('email.composer.untitled') })
      }
    >
      <div className="space-y-4">
        {!isNew && (
          <div className="flex items-center gap-2">
            <StatusBadge status={status} />
            {campaign?.mailchimp_campaign_id && <span className="text-xs text-slate-400">{t('email.composer.mailchimpId', { id: campaign.mailchimp_campaign_id })}</span>}
          </div>
        )}

        {anyError && (
          <p role="alert" className="text-sm font-medium text-red-600">{apiErrorMessage(anyError, 'email.error')}</p>
        )}

        <Input label={t('email.composer.subject')} value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!isDraft && !isNew} />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input label={t('email.composer.fromName')} value={fromName} onChange={(e) => setFromName(e.target.value)} disabled={!isDraft && !isNew} />
          <Input
            label={t('email.composer.fromEmail')}
            value={fromEmail}
            onChange={(e) => setFromEmail(e.target.value)}
            disabled={!isDraft && !isNew}
          />
        </div>
        <p className="-mt-2 text-xs text-slate-400">{t('email.composer.fromEmailHelp')}</p>

        <Input label={t('email.composer.replyTo')} type="email" value={replyTo} onChange={(e) => setReplyTo(e.target.value)} disabled={!isDraft && !isNew} />

        <div>
          <label htmlFor="campaign-audience" className="mb-1 block text-base font-medium text-slate-700">{t('email.composer.audience')}</label>
          {isDraft || isNew ? (
            <select
              id="campaign-audience"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base shadow-sm outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
              value={audienceId}
              onChange={(e) => {
                setAudienceId(e.target.value)
                setAudienceName(audiences?.find((a) => a.id === e.target.value)?.name || '')
              }}
            >
              <option value="">{t('email.composer.selectAudience')}</option>
              {audiences?.map((a) => (
                <option key={a.id} value={a.id}>
                  {t('email.composer.audienceOption', { name: a.name, count: a.member_count })}
                </option>
              ))}
            </select>
          ) : (
            <p className="text-sm text-slate-700">{audienceName || audienceId}</p>
          )}
        </div>

        <div>
          <label htmlFor="campaign-body" className="mb-1 block text-base font-medium text-slate-700">{t('email.composer.body')}</label>
          <textarea
            id="campaign-body"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            rows={10}
            value={bodyHtml}
            onChange={(e) => setBodyHtml(e.target.value)}
            disabled={!isDraft && !isNew}
            placeholder={t('email.composer.bodyPlaceholder')}
          />
        </div>

        {bodyHtml && (
          <div>
            <p className="mb-1 text-sm font-medium text-slate-500">{t('email.composer.preview')}</p>
            {/* Sandboxed (no scripts, no same-origin access): the HTML is shown as
                the email would look, but nothing in it can run on app.mielikkix.ai. */}
            <iframe
              title={t('email.composer.previewTitle')}
              sandbox=""
              srcDoc={bodyHtml}
              className="h-64 w-full rounded-xl border border-slate-200 bg-white"
            />
          </div>
        )}

        {(isDraft || isNew) && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" loading={saveMut.isPending} onClick={() => saveMut.mutate()}>
              {savedId ? t('email.composer.saveChanges') : t('email.composer.saveDraft')}
            </Button>
            {savedId && (
              <Button size="sm" loading={approveMut.isPending} onClick={() => approveMut.mutate()}>
                {t('email.composer.approve')}
              </Button>
            )}
          </div>
        )}

        {savedId && isSendable && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <div className="flex flex-wrap items-end gap-2">
              <Input
                label={t('email.composer.testTo')}
                className="min-w-[240px] flex-1"
                value={testEmails}
                onChange={(e) => setTestEmails(e.target.value)}
                placeholder={t('email.composer.testPlaceholder')}
              />
              <Button size="sm" variant="secondary" loading={testMut.isPending} onClick={() => testMut.mutate()} disabled={!testEmails.trim()}>
                <FlaskConical size={14} className="mr-1" />
                {t('email.composer.sendTest')}
              </Button>
            </div>

            <div className="flex flex-wrap items-end gap-2">
              <Input
                label={t('email.composer.scheduleFor')}
                type="datetime-local"
                className="min-w-[220px]"
                value={scheduleAt}
                onChange={(e) => setScheduleAt(e.target.value)}
              />
              <Button size="sm" variant="secondary" loading={scheduleMut.isPending} onClick={() => scheduleMut.mutate()} disabled={!scheduleAt}>
                <Clock size={14} className="mr-1" />
                {t('email.composer.schedule')}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              {!confirmingSend ? (
                <Button size="sm" variant="danger" onClick={() => setConfirmingSend(true)}>
                  <Send size={14} className="mr-1" />
                  {t('email.composer.sendNow')}
                </Button>
              ) : (
                <>
                  <Button size="sm" variant="danger" loading={sendMut.isPending} onClick={() => sendMut.mutate()}>
                    {t('email.composer.confirmSend', { audience: audienceName || t('email.composer.thisAudience') })}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmingSend(false)}>
                    {t('email.composer.cancel')}
                  </Button>
                </>
              )}
            </div>
          </div>
        )}

        {savedId && hasReport && (
          <div className="space-y-2 border-t border-slate-100 pt-4">
            <Button size="sm" variant="secondary" onClick={() => setShowReport((v) => !v)}>
              <BarChart3 size={14} className="mr-1" />
              {showReport ? t('email.composer.hideReport') : t('email.composer.showReport')}
            </Button>
            {showReport && <CampaignReportPanel campaignId={savedId} />}
          </div>
        )}

        <div className="border-t border-slate-100 pt-4">
          <Button size="sm" variant="ghost" onClick={onClose}>
            {t('email.composer.close')}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function CampaignsSection({ mailchimpStatus }: { mailchimpStatus?: MailchimpStatus }) {
  const [selected, setSelected] = useState<Campaign | null | 'new'>(null)
  const { t } = useT()

  const { data: campaigns, isLoading } = useQuery<Campaign[]>({
    queryKey: ['campaigns'],
    queryFn: () => api.get('/businesses/me/campaigns').then((r) => r.data),
  })

  if (selected !== null) {
    return (
      <CampaignComposer
        campaign={selected === 'new' ? null : selected}
        mailchimpStatus={mailchimpStatus}
        onClose={() => setSelected(null)}
      />
    )
  }

  return (
    <Card title={t('email.campaigns.title')}>
      <div className="space-y-3">
        <Button size="sm" onClick={() => setSelected('new')}>
          <Plus size={14} className="mr-1" />
          {t('email.campaigns.new')}
        </Button>

        {isLoading && <p className="text-sm text-slate-500">{t('email.campaigns.loading')}</p>}

        {!isLoading && (!campaigns || campaigns.length === 0) && (
          <p className="text-sm text-slate-500">{t('email.campaigns.empty')}</p>
        )}

        <div className="space-y-2">
          {campaigns?.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c)}
              className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-3 text-left hover:bg-slate-50"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{c.subject || t('email.campaigns.untitled')}</p>
                <p className="truncate text-xs text-slate-500">{c.mailchimp_audience_name || t('email.campaigns.noAudience')}</p>
              </div>
              <StatusBadge status={c.status} />
            </button>
          ))}
        </div>
      </div>
    </Card>
  )
}

function EmailMarketingPageContent() {
  const { t } = useT()
  const { data: status, isLoading } = useQuery<MailchimpStatus>({
    queryKey: ['mailchimp-status'],
    queryFn: () => api.get('/businesses/me/mailchimp/status').then((r) => r.data),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">{t('email.title')}</h1>
        <p className="mt-1 text-slate-500">{t('email.subtitle')}</p>
      </div>
      <MailchimpConnectionCard status={status} isLoading={isLoading} />
      {status?.connected && <CampaignsSection mailchimpStatus={status} />}
    </div>
  )
}

export function EmailMarketingPage() {
  const { data: access, isLoading } = useAgentAccess()
  const { t } = useT()
  if (isLoading) return null

  if (!access?.email_marketing) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">{t('email.title')}</h1>
        <AgentGate agentKey="email_marketing">
          <span />
        </AgentGate>
      </div>
    )
  }

  return <EmailMarketingPageContent />
}
