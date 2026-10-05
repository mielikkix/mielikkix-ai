import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, MessageSquare, AlertTriangle, Check, X, RefreshCw, Pencil, Download, Send, Flag } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { AgentGate } from '../../shared/components/AgentGate'
import { useAgentAccess } from '../../shared/hooks/usePlan'
import { useT } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

interface Review {
  id: string
  platform: string
  external_review_id: string | null
  customer_name: string | null
  rating: number | null
  review_text: string
  review_language: string | null
  sentiment: 'positive' | 'neutral' | 'negative' | 'mixed' | null
  sentiment_score: number | null
  topics: string[]
  positive_points: string[]
  negative_points: string[]
  primary_issue: string | null
  priority: 'low' | 'medium' | 'high' | 'critical'
  requires_response: boolean
  requires_human_review: boolean
  escalation_reason: string | null
  risk_reasons: string[]
  ai_response: string | null
  response_tone: string | null
  response_status: 'none' | 'draft' | 'approved' | 'rejected' | 'published'
  published_response: string | null
  published_at: string | null
  analyzed_at: string | null
}

interface GoogleReviewsStatus {
  connected: boolean
  needs_location: boolean
  configured: boolean
  google_account_email?: string | null
  location_title?: string | null
  connected_at?: string
}

interface LocationOption {
  location_id: string
  title: string
}

interface Insights {
  review_count: number
  average_rating: number | null
  sentiment_breakdown: Record<string, number>
  top_positive_topics: { topic: string; count: number }[]
  top_negative_topics: { topic: string; count: number }[]
  reviews_requiring_attention: number
  insufficient_data: boolean
  summary: string | null
  // every review in the window, and how many still wait for (or failed) AI analysis
  total_reviews: number
  unanalyzed_count: number
}

// Platform/sentiment/priority/topic/escalation values are API codes; their
// labels live under reviews.* in the i18n messages ("mock" = the demo data
// added by "Import sample reviews").
const TONES = ['professional', 'friendly', 'warm', 'luxury', 'casual', 'concise', 'empathetic']

interface Trends {
  current_period_days: number
  current_negative_pct: number | null
  previous_negative_pct: number | null
  negative_trend: 'improving' | 'declining' | 'stable' | null
  recurring_negative_topics: { topic: string; count: number }[]
  sudden_spike: boolean
  insufficient_data: boolean
}

// Which platforms actually implement ReviewResponsePublisher server-side
// (see integrations/review_platforms/{google_platform,mock_platform}.py)
// -- showing a Publish button for anything else (a manually-typed or
// chat-entered review has no real external reply target) would just
// produce a guaranteed 400 the moment it's clicked, so it's hidden
// entirely for those instead.
const PUBLISHABLE_PLATFORMS = new Set(['google', 'mock'])

const SENTIMENT_COLORS: Record<string, string> = {
  positive: 'bg-emerald-50 text-emerald-700',
  neutral: 'bg-slate-100 text-slate-600',
  negative: 'bg-red-50 text-red-700',
  mixed: 'bg-amber-50 text-amber-700',
}

const PRIORITY_COLORS: Record<string, string> = {
  low: 'bg-slate-100 text-slate-500',
  medium: 'bg-amber-50 text-amber-700',
  high: 'bg-orange-50 text-orange-700',
  critical: 'bg-red-100 text-red-800',
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="text-center">
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      <p className="mt-1 text-sm text-slate-500">{label}</p>
    </Card>
  )
}

// Real per-tenant Google Business Profile connection (see
// app/api/review_oauth.py) -- the first step of "Google Reviews -> Analyze
// -> Draft -> Approve -> Publish". Self-contained (owns its own queries/
// mutations/banner state) rather than threaded through ReviewsPageContent's
// props, the same reasoning ReviewCard below already follows per-review.
function GoogleConnectionCard() {
  const qc = useQueryClient()
  const { t } = useT()
  const [searchParams, setSearchParams] = useSearchParams()
  const [banner, setBanner] = useState<'connected' | 'error' | 'choose_location' | null>(null)

  useEffect(() => {
    const value = searchParams.get('google_reviews')
    if (value === 'connected' || value === 'error' || value === 'choose_location') {
      setBanner(value)
      qc.invalidateQueries({ queryKey: ['review-google-status'] })
      const next = new URLSearchParams(searchParams)
      next.delete('google_reviews')
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { data: status } = useQuery<GoogleReviewsStatus>({
    queryKey: ['review-google-status'],
    queryFn: () => api.get('/businesses/me/reviews/status').then((r) => r.data),
  })

  const needsLocation = banner === 'choose_location' || status?.needs_location

  const { data: locations } = useQuery<LocationOption[]>({
    queryKey: ['review-google-locations'],
    queryFn: () => api.get('/businesses/me/reviews/locations').then((r) => r.data),
    enabled: !!needsLocation,
  })

  const selectLocationMut = useMutation({
    mutationFn: (location: LocationOption) =>
      api.post('/businesses/me/reviews/select-location', { location_id: location.location_id, title: location.title }),
    onSuccess: () => {
      setBanner('connected')
      qc.invalidateQueries({ queryKey: ['review-google-status'] })
    },
  })

  const disconnectMut = useMutation({
    mutationFn: () => api.delete('/businesses/me/reviews'),
    onSuccess: () => {
      setBanner(null)
      qc.invalidateQueries({ queryKey: ['review-google-status'] })
    },
  })

  return (
    <Card title={t('reviews.google.title')}>
      <div className="space-y-3">
        {banner === 'error' && <p role="alert" className="text-sm text-red-600">{t('reviews.google.connectFailed')}</p>}
        {needsLocation ? (
          <>
            <p className="text-sm text-slate-500">
              {status?.google_account_email
                ? t('reviews.google.connectedAs', { email: status.google_account_email })
                : t('reviews.google.connectedPlain')}{' '}
              {t('reviews.google.chooseLocation')}
            </p>
            <div className="flex flex-wrap gap-2">
              {(locations ?? []).map((loc) => (
                <Button
                  key={loc.location_id}
                  size="sm"
                  variant="secondary"
                  loading={selectLocationMut.isPending}
                  onClick={() => selectLocationMut.mutate(loc)}
                >
                  {loc.title}
                </Button>
              ))}
              {locations?.length === 0 && <p className="text-sm text-slate-400">{t('reviews.google.noLocations')}</p>}
            </div>
          </>
        ) : status?.connected ? (
          <>
            {banner === 'connected' && <p role="status" className="text-sm text-emerald-600">{t('reviews.google.connectedBanner')}</p>}
            <p className="text-sm text-slate-700">
              {status.google_account_email
                ? t('reviews.google.connectedAs', { email: status.google_account_email })
                : t('reviews.google.connectedPlain')}
              {status.location_title && <> {t('reviews.google.location', { name: status.location_title })}</>}
            </p>
            <Button variant="secondary" size="sm" loading={disconnectMut.isPending} onClick={() => disconnectMut.mutate()}>
              {t('reviews.google.disconnect')}
            </Button>
          </>
        ) : status && !status.configured ? (
          // QA 2026-10-02 (D5): this read "isn't set up for this environment yet" -- developer wording. The
          // Google Business Profile API needs Google's approval of our app, which is still pending.
          <p className="text-sm text-slate-500">
            <span className="mr-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700">{t('reviews.google.soonBadge')}</span>
            {t('reviews.google.soonText')}
          </p>
        ) : (
          <>
            <p className="text-sm text-slate-500">{t('reviews.google.connectHelp')}</p>
            <Button
              size="sm"
              onClick={() => {
                window.location.href = `${api.defaults.baseURL}/businesses/me/reviews/authorize`
              }}
            >
              {t('reviews.google.connect')}
            </Button>
          </>
        )}
      </div>
    </Card>
  )
}

function ReviewCard({ review }: { review: Review }) {
  const qc = useQueryClient()
  const { t, tCode, formatDateTime } = useT()
  const platformName = tCode('reviews.platforms', review.platform)
  const [expanded, setExpanded] = useState(false)
  const [editedResponse, setEditedResponse] = useState<string | null>(null)
  const [tone, setTone] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['reviews'] })
    qc.invalidateQueries({ queryKey: ['reviews', 'insights'] })
  }

  const analyzeMut = useMutation({
    mutationFn: () => api.post(`/agents/reviews/${review.id}/analyze`),
    onSuccess: invalidate,
  })
  const generateMut = useMutation({
    mutationFn: () => api.post(`/agents/reviews/${review.id}/generate-response`, tone ? { tone } : {}),
    onSuccess: invalidate,
  })
  const editMut = useMutation({
    mutationFn: (text: string) => api.patch(`/agents/reviews/${review.id}/response`, { response_text: text }),
    onSuccess: () => {
      invalidate()
      setEditedResponse(null)
    },
  })
  const approveMut = useMutation({
    mutationFn: () => api.post(`/agents/reviews/${review.id}/approve`),
    onSuccess: invalidate,
  })
  const rejectMut = useMutation({
    mutationFn: () => api.post(`/agents/reviews/${review.id}/reject`),
    onSuccess: invalidate,
  })
  const publishMut = useMutation({
    mutationFn: () => api.post(`/agents/reviews/${review.id}/publish`),
    onSuccess: invalidate,
  })
  // One customer-facing action for "approve this response and post it live
  // on the review platform" -- saves an in-progress edit first (so typing
  // a reply from scratch, or editing the AI draft, and immediately
  // clicking this Just Works without a separate "Save edit" click), then
  // reuses the existing approve + publish endpoints exactly as they are.
  // No new backend endpoint, no second publishing path: this is the same
  // /approve + /publish this page already calls, just chained in one click.
  const approveAndPublishMut = useMutation({
    mutationFn: async () => {
      if (editedResponse != null && editedResponse !== review.ai_response) {
        await api.patch(`/agents/reviews/${review.id}/response`, { response_text: editedResponse })
      }
      await api.post(`/agents/reviews/${review.id}/approve`)
      await api.post(`/agents/reviews/${review.id}/publish`)
    },
    onSuccess: () => {
      invalidate()
      setEditedResponse(null)
    },
  })
  const escalateMut = useMutation({
    mutationFn: () => api.post(`/agents/reviews/${review.id}/escalate`),
    onSuccess: invalidate,
  })

  return (
    <Card>
      <div className="flex cursor-pointer items-start justify-between gap-4" onClick={() => setExpanded((e) => !e)}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">{review.customer_name || t('reviews.card.anonymous')}</span>
            {review.platform === 'mock' ? (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {t('reviews.card.sample')}
              </span>
            ) : (
              <span className="text-xs uppercase tracking-wide text-slate-400">{platformName}</span>
            )}
            {review.rating != null && (
              <span
                className="flex items-center gap-0.5 text-amber-500"
                role="img"
                aria-label={t('reviews.card.stars', { count: review.rating })}
              >
                {Array.from({ length: review.rating }).map((_, i) => (
                  <Star key={i} size={13} fill="currentColor" strokeWidth={0} />
                ))}
              </span>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-slate-600">{review.review_text}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {review.sentiment && (
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${SENTIMENT_COLORS[review.sentiment]}`}>
              {tCode('reviews.sentiments', review.sentiment)}
            </span>
          )}
          {!review.analyzed_at && (
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">{t('reviews.card.notAnalyzed')}</span>
          )}
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${PRIORITY_COLORS[review.priority]}`}>
            {tCode('reviews.priorities', review.priority)}
          </span>
          {review.requires_human_review && (
            <span className="flex items-center gap-1 text-xs font-medium text-red-600">
              <AlertTriangle size={12} /> {t('reviews.card.needsHuman')}
            </span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
          {review.analyzed_at ? (
            <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
              <div>
                <p className="font-medium text-slate-500">{t('reviews.card.topics')}</p>
                <p className="text-slate-800">{review.topics.map((topic) => tCode('reviews.topics', topic)).join(', ') || '-'}</p>
              </div>
              <div>
                <p className="font-medium text-slate-500">{t('reviews.card.primaryIssue')}</p>
                <p className="text-slate-800">{review.primary_issue || '-'}</p>
              </div>
              {review.positive_points.length > 0 && (
                <div>
                  <p className="font-medium text-emerald-600">{t('reviews.card.positive')}</p>
                  <p className="text-slate-800">{review.positive_points.join('; ')}</p>
                </div>
              )}
              {review.negative_points.length > 0 && (
                <div>
                  <p className="font-medium text-red-600">{t('reviews.card.negative')}</p>
                  <p className="text-slate-800">{review.negative_points.join('; ')}</p>
                </div>
              )}
              {review.escalation_reason && (
                <div className="md:col-span-2 rounded-lg bg-red-50 px-3 py-2 text-red-700">
                  {t('reviews.card.escalationReason')} <strong>{tCode('reviews.escalations', review.escalation_reason)}</strong>
                  {review.risk_reasons.length > 1 && (
                    <span className="block text-xs text-red-600">
                      {t('reviews.card.alsoFlagged', {
                        reasons: review.risk_reasons
                          .filter((r) => r !== review.escalation_reason)
                          .map((r) => tCode('reviews.escalations', r))
                          .join(', '),
                      })}
                    </span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <Button size="sm" variant="secondary" loading={analyzeMut.isPending} onClick={() => analyzeMut.mutate()}>
              {t('reviews.card.analyze')}
            </Button>
          )}

          <div>
            <label htmlFor={`review-response-${review.id}`} className="text-sm font-medium text-slate-500">
              {review.ai_response ? t('reviews.card.suggested') : t('reviews.card.writeOwn')}
            </label>
            <textarea
              id={`review-response-${review.id}`}
              className="mt-1 w-full rounded-lg border border-slate-200 p-2.5 text-sm text-slate-800 outline-none focus:border-violet-400"
              rows={3}
              placeholder={t('reviews.card.responsePlaceholder')}
              value={editedResponse ?? review.ai_response ?? ''}
              onChange={(e) => setEditedResponse(e.target.value)}
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                aria-label={t('reviews.card.toneLabel')}
                className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm text-slate-600"
              >
                <option value="">{t('reviews.tones.default')}</option>
                {TONES.map((tone) => (
                  <option key={tone} value={tone}>
                    {tCode('reviews.tones', tone)}
                  </option>
                ))}
              </select>
              <Button size="sm" variant="secondary" loading={generateMut.isPending} onClick={() => generateMut.mutate()}>
                <RefreshCw size={14} className="mr-1" />
                {review.ai_response ? t('reviews.card.regenerate') : t('reviews.card.generate')}
              </Button>
              {editedResponse != null && editedResponse !== review.ai_response && (
                <Button size="sm" variant="secondary" loading={editMut.isPending} onClick={() => editMut.mutate(editedResponse)}>
                  <Pencil size={14} className="mr-1" />
                  {t('reviews.card.saveEdit')}
                </Button>
              )}
              {(review.ai_response || (editedResponse && editedResponse.trim())) && review.response_status !== 'published' && (
                <>
                  {PUBLISHABLE_PLATFORMS.has(review.platform) ? (
                    <Button
                      size="sm"
                      loading={approveAndPublishMut.isPending}
                      disabled={review.requires_human_review || !(editedResponse ?? review.ai_response ?? '').trim()}
                      onClick={() => approveAndPublishMut.mutate()}
                    >
                      <Send size={14} className="mr-1" />
                      {review.response_status === 'approved'
                        ? t('reviews.card.replyOn', { platform: platformName })
                        : t('reviews.card.approveReplyOn', { platform: platformName })}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      loading={approveMut.isPending}
                      disabled={review.response_status === 'approved'}
                      onClick={() => approveMut.mutate()}
                    >
                      <Check size={14} className="mr-1" />
                      {review.response_status === 'approved' ? t('reviews.card.approved') : t('reviews.card.approve')}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
                    <X size={14} className="mr-1" />
                    {t('reviews.card.reject')}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={escalateMut.isPending}
                    disabled={review.requires_human_review}
                    onClick={() => escalateMut.mutate()}
                  >
                    <Flag size={14} className="mr-1" />
                    {review.requires_human_review ? t('reviews.card.escalated') : t('reviews.card.escalate')}
                  </Button>
                </>
              )}
            </div>
            {(publishMut.isError || approveAndPublishMut.isError) && (
              <p role="alert" className="mt-2 text-xs font-medium text-red-600">
                {apiErrorMessage(approveAndPublishMut.error ?? publishMut.error, 'reviews.card.publishFailed')}
              </p>
            )}
            {review.response_status === 'approved' && review.requires_human_review && (
              <p className="mt-2 text-xs font-medium text-red-600">
                {t('reviews.card.flagged', { platform: platformName })}
              </p>
            )}
            {review.response_status === 'approved' && !PUBLISHABLE_PLATFORMS.has(review.platform) && (
              <p className="mt-2 text-xs text-slate-400">
                {t('reviews.card.manualPost', { platform: platformName })}
              </p>
            )}
            {review.response_status === 'published' && (
              <div className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                <p className="font-medium">
                  {review.published_at
                    ? t('reviews.card.publishedOn', { platform: platformName, date: formatDateTime(review.published_at) })
                    : t('reviews.card.published', { platform: platformName })}
                </p>
                {review.published_response && <p className="mt-1 text-emerald-800">{review.published_response}</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}

function ReviewsPageContent() {
  const qc = useQueryClient()
  const { t, tCode, formatNumber } = useT()
  const [priority, setPriority] = useState('')
  const [sentiment, setSentiment] = useState('')
  const [attentionOnly, setAttentionOnly] = useState(false)
  const [newReviewText, setNewReviewText] = useState('')
  const [newReviewRating, setNewReviewRating] = useState('')

  const { data: reviews = [] } = useQuery<Review[]>({
    queryKey: ['reviews', priority, sentiment, attentionOnly],
    queryFn: () =>
      api
        .get('/agents/reviews', {
          params: {
            priority: priority || undefined,
            sentiment: sentiment || undefined,
            requires_human_review: attentionOnly || undefined,
          },
        })
        .then((r) => r.data),
  })

  const {
    data: insights,
    isError: insightsFailed,
    refetch: refetchInsights,
  } = useQuery<Insights>({
    queryKey: ['reviews', 'insights'],
    queryFn: () => api.get('/agents/reviews/insights').then((r) => r.data),
  })
  const hasSamples = reviews.some((r) => r.platform === 'mock')

  const analyzePendingMut = useMutation({
    mutationFn: () => api.post('/agents/reviews/analyze-pending').then((r) => r.data as { analyzed: number; still_pending: number }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['reviews'] }),
  })

  const deleteSamplesMut = useMutation({
    mutationFn: () => api.delete('/agents/reviews/samples'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviews'] }),
  })

  const { data: trends } = useQuery<Trends>({
    queryKey: ['reviews', 'trends'],
    queryFn: () => api.get('/agents/reviews/trends').then((r) => r.data),
  })

  const addMut = useMutation({
    mutationFn: () =>
      api.post('/agents/reviews', {
        review_text: newReviewText,
        rating: newReviewRating ? Number(newReviewRating) : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reviews'] })
      setNewReviewText('')
      setNewReviewRating('')
    },
  })

  const importMut = useMutation({
    mutationFn: () => api.post('/agents/reviews/import', { platform: 'mock' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reviews'] })
      qc.invalidateQueries({ queryKey: ['reviews', 'insights'] })
    },
  })

  // Reads the SAME cache GoogleConnectionCard's own useQuery already
  // populates (react-query dedupes by queryKey) -- this component doesn't
  // own the connection, it just needs to know whether "Import from
  // Google" is actually usable yet.
  const { data: googleStatus } = useQuery<GoogleReviewsStatus>({
    queryKey: ['review-google-status'],
    queryFn: () => api.get('/businesses/me/reviews/status').then((r) => r.data),
  })
  const importGoogleMut = useMutation({
    mutationFn: () => api.post('/agents/reviews/import', { platform: 'google' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reviews'] })
      qc.invalidateQueries({ queryKey: ['reviews', 'insights'] })
    },
  })

  const reputationScore = insights?.average_rating != null ? Math.round((insights.average_rating / 5) * 100) : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">{t('reviews.title')}</h1>
          <p className="mt-1 text-base text-slate-500">{t('reviews.subtitle')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {googleStatus?.connected && (
            <Button size="sm" loading={importGoogleMut.isPending} onClick={() => importGoogleMut.mutate()}>
              <Download size={16} className="mr-1" />
              {t('reviews.importGoogle')}
            </Button>
          )}
          {hasSamples ? (
            <Button size="sm" variant="secondary" loading={deleteSamplesMut.isPending} onClick={() => deleteSamplesMut.mutate()}>
              <X size={16} className="mr-1" />
              {t('reviews.removeSamples')}
            </Button>
          ) : (
            <Button size="sm" variant="secondary" loading={importMut.isPending} onClick={() => importMut.mutate()}>
              <Download size={16} className="mr-1" />
              {t('reviews.importSamples')}
            </Button>
          )}
        </div>
      </div>
      {importGoogleMut.isError && (
        <p role="alert" className="text-sm font-medium text-red-600">{apiErrorMessage(importGoogleMut.error, 'reviews.importGoogleFailed')}</p>
      )}

      <GoogleConnectionCard />

      {/* QA 2026-10-02 (D1): when stats failed to load these used to show "0" next to a list of 8 reviews. */}
      {insightsFailed && (
        <p className="flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <AlertTriangle size={16} /> {t('reviews.stats.loadFailed')}
          <button className="font-semibold underline" onClick={() => refetchInsights()}>
            {t('reviews.stats.retry')}
          </button>
        </p>
      )}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <StatCard label={t('reviews.stats.score')} value={reputationScore != null ? formatNumber(reputationScore) : '-'} />
        <StatCard
          label={t('reviews.stats.average')}
          value={insights?.average_rating != null ? formatNumber(insights.average_rating, 1) : '-'}
        />
        <StatCard
          label={t('reviews.stats.total')}
          value={insights ? formatNumber(insights.total_reviews ?? insights.review_count) : '-'}
        />
        <StatCard
          label={t('reviews.stats.positive')}
          value={insights && !insights.insufficient_data ? `${formatNumber(insights.sentiment_breakdown.positive ?? 0)} %` : '-'}
        />
        <StatCard
          label={t('reviews.stats.negative')}
          value={insights && !insights.insufficient_data ? `${formatNumber(insights.sentiment_breakdown.negative ?? 0)} %` : '-'}
        />
        <StatCard label={t('reviews.stats.attention')} value={insights ? formatNumber(insights.reviews_requiring_attention) : '-'} />
      </div>

      {(insights?.unanalyzed_count ?? 0) > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          <span>
            {t('reviews.unanalyzed', { count: insights!.unanalyzed_count })}
            {analyzePendingMut.data && analyzePendingMut.data.still_pending > 0 && ` ${t('reviews.analysisFailing')}`}
          </span>
          <Button size="sm" variant="secondary" loading={analyzePendingMut.isPending} onClick={() => analyzePendingMut.mutate()}>
            <RefreshCw size={14} className="mr-1" /> {t('reviews.analyzeNow')}
          </Button>
        </div>
      )}

      {insights?.insufficient_data ? (
        <Card>
          <p className="text-sm text-slate-400">{t('reviews.notEnough')}</p>
        </Card>
      ) : (
        <Card title={t('reviews.insights')}>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div>
              <p className="text-sm font-medium text-emerald-600">{t('reviews.topPositive')}</p>
              <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
                {(insights?.top_positive_topics ?? []).map((item) => (
                  <li key={item.topic}>
                    {tCode('reviews.topics', item.topic)} ({formatNumber(item.count)})
                  </li>
                ))}
                {insights?.top_positive_topics.length === 0 && <li className="text-slate-400">{t('reviews.noneYet')}</li>}
              </ul>
            </div>
            <div>
              <p className="text-sm font-medium text-red-600">{t('reviews.topNegative')}</p>
              <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
                {(insights?.top_negative_topics ?? []).map((item) => (
                  <li key={item.topic}>
                    {tCode('reviews.topics', item.topic)} ({formatNumber(item.count)})
                  </li>
                ))}
                {insights?.top_negative_topics.length === 0 && <li className="text-slate-400">{t('reviews.noneYet')}</li>}
              </ul>
            </div>
          </div>
          {insights?.summary && <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">{insights.summary}</p>}
          {trends && !trends.insufficient_data && trends.sudden_spike && (
            <p className="mt-3 flex items-center gap-1.5 rounded-xl bg-red-50 p-3 text-sm text-red-700">
              <AlertTriangle size={16} />
              {t('reviews.spike', {
                previous: trends.previous_negative_pct ?? 0,
                current: trends.current_negative_pct ?? 0,
                days: trends.current_period_days,
              })}
              {trends.recurring_negative_topics[0] &&
                ` ${t('reviews.mostMentioned', { topic: tCode('reviews.topics', trends.recurring_negative_topics[0].topic) })}`}
            </p>
          )}
        </Card>
      )}

      <Card title={t('reviews.log.title')}>
        <div className="flex flex-col gap-2 md:flex-row">
          <input
            type="text"
            value={newReviewText}
            onChange={(e) => setNewReviewText(e.target.value)}
            placeholder={t('reviews.log.textPlaceholder')}
            aria-label={t('reviews.log.textLabel')}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-violet-400"
          />
          <input
            type="number"
            min={1}
            max={5}
            value={newReviewRating}
            onChange={(e) => setNewReviewRating(e.target.value)}
            placeholder={t('reviews.log.ratingPlaceholder')}
            aria-label={t('reviews.log.ratingLabel')}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-violet-400 md:w-40"
          />
          <Button size="sm" disabled={!newReviewText.trim()} loading={addMut.isPending} onClick={() => addMut.mutate()}>
            <MessageSquare size={16} className="mr-1" />
            {t('reviews.log.add')}
          </Button>
        </div>
      </Card>

      <div className="flex flex-wrap gap-2">
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          aria-label={t('reviews.filters.priority')}
          className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
        >
          <option value="">{t('reviews.filters.allPriorities')}</option>
          {['low', 'medium', 'high', 'critical'].map((p) => (
            <option key={p} value={p}>
              {tCode('reviews.priorities', p)}
            </option>
          ))}
        </select>
        <select
          value={sentiment}
          onChange={(e) => setSentiment(e.target.value)}
          aria-label={t('reviews.filters.sentiment')}
          className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
        >
          <option value="">{t('reviews.filters.allSentiments')}</option>
          {['positive', 'neutral', 'negative', 'mixed'].map((s) => (
            <option key={s} value={s}>
              {tCode('reviews.sentiments', s)}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2 py-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={attentionOnly} onChange={(e) => setAttentionOnly(e.target.checked)} />
          {t('reviews.filters.attentionOnly')}
        </label>
      </div>

      <div className="space-y-3">
        {reviews.map((review) => (
          <ReviewCard key={review.id} review={review} />
        ))}
        {reviews.length === 0 && (
          <div className="py-12 text-center text-base text-slate-400">{t('reviews.empty')}</div>
        )}
      </div>
    </div>
  )
}

export function ReviewsPage() {
  const { data: access, isLoading } = useAgentAccess()
  const { t } = useT()
  if (isLoading) return null

  if (!access?.review_reputation) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">{t('reviews.title')}</h1>
        <AgentGate agentKey="review_reputation">
          <span />
        </AgentGate>
      </div>
    )
  }

  return <ReviewsPageContent />
}
