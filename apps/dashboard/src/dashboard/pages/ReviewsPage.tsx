import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, MessageSquare, AlertTriangle, Check, X, RefreshCw, Pencil, Download } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { PlanGate } from '../../shared/components/PlanGate'
import { usePlan } from '../../shared/hooks/usePlan'

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
  ai_response: string | null
  response_tone: string | null
  response_status: 'none' | 'draft' | 'approved' | 'rejected' | 'published'
  analyzed_at: string | null
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
}

interface Trends {
  current_period_days: number
  current_negative_pct: number | null
  previous_negative_pct: number | null
  negative_trend: 'improving' | 'declining' | 'stable' | null
  recurring_negative_topics: { topic: string; count: number }[]
  sudden_spike: boolean
  insufficient_data: boolean
}

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

function ReviewCard({ review }: { review: Review }) {
  const qc = useQueryClient()
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

  return (
    <Card>
      <div className="flex cursor-pointer items-start justify-between gap-4" onClick={() => setExpanded((e) => !e)}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">{review.customer_name || 'Anonymous'}</span>
            <span className="text-xs uppercase tracking-wide text-slate-400">{review.platform}</span>
            {review.rating != null && (
              <span className="flex items-center gap-0.5 text-amber-500">
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
              {review.sentiment}
            </span>
          )}
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${PRIORITY_COLORS[review.priority]}`}>
            {review.priority}
          </span>
          {review.requires_human_review && (
            <span className="flex items-center gap-1 text-xs font-medium text-red-600">
              <AlertTriangle size={12} /> needs a human
            </span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
          {review.analyzed_at ? (
            <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
              <div>
                <p className="font-medium text-slate-500">Topics</p>
                <p className="text-slate-800">{review.topics.join(', ') || '-'}</p>
              </div>
              <div>
                <p className="font-medium text-slate-500">Primary issue</p>
                <p className="text-slate-800">{review.primary_issue || '-'}</p>
              </div>
              {review.positive_points.length > 0 && (
                <div>
                  <p className="font-medium text-emerald-600">Positive</p>
                  <p className="text-slate-800">{review.positive_points.join('; ')}</p>
                </div>
              )}
              {review.negative_points.length > 0 && (
                <div>
                  <p className="font-medium text-red-600">Negative</p>
                  <p className="text-slate-800">{review.negative_points.join('; ')}</p>
                </div>
              )}
              {review.escalation_reason && (
                <div className="md:col-span-2 rounded-lg bg-red-50 px-3 py-2 text-red-700">
                  Escalation reason: <strong>{review.escalation_reason}</strong>
                </div>
              )}
            </div>
          ) : (
            <Button size="sm" variant="secondary" loading={analyzeMut.isPending} onClick={() => analyzeMut.mutate()}>
              Analyze
            </Button>
          )}

          <div>
            <p className="text-sm font-medium text-slate-500">Suggested response</p>
            {review.ai_response ? (
              <textarea
                className="mt-1 w-full rounded-lg border border-slate-200 p-2.5 text-sm text-slate-800 outline-none focus:border-violet-400"
                rows={3}
                value={editedResponse ?? review.ai_response}
                onChange={(e) => setEditedResponse(e.target.value)}
              />
            ) : (
              <p className="mt-1 text-sm text-slate-400">No response generated yet.</p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm text-slate-600"
              >
                <option value="">Business default tone</option>
                {['professional', 'friendly', 'warm', 'luxury', 'casual', 'concise', 'empathetic'].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <Button size="sm" variant="secondary" loading={generateMut.isPending} onClick={() => generateMut.mutate()}>
                <RefreshCw size={14} className="mr-1" />
                {review.ai_response ? 'Regenerate' : 'Generate response'}
              </Button>
              {editedResponse != null && editedResponse !== review.ai_response && (
                <Button size="sm" variant="secondary" loading={editMut.isPending} onClick={() => editMut.mutate(editedResponse)}>
                  <Pencil size={14} className="mr-1" />
                  Save edit
                </Button>
              )}
              {review.ai_response && (
                <>
                  <Button
                    size="sm"
                    loading={approveMut.isPending}
                    disabled={review.response_status === 'approved'}
                    onClick={() => approveMut.mutate()}
                  >
                    <Check size={14} className="mr-1" />
                    {review.response_status === 'approved' ? 'Approved' : 'Approve'}
                  </Button>
                  <Button size="sm" variant="ghost" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
                    <X size={14} className="mr-1" />
                    Reject
                  </Button>
                </>
              )}
            </div>
            {review.response_status === 'approved' && (
              <p className="mt-2 text-xs text-slate-400">
                Approved -- publishing to {review.platform} isn't connected yet, so post this manually for now.
              </p>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}

function ReviewsPageContent() {
  const qc = useQueryClient()
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

  const { data: insights } = useQuery<Insights>({
    queryKey: ['reviews', 'insights'],
    queryFn: () => api.get('/agents/reviews/insights').then((r) => r.data),
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

  const reputationScore = insights?.average_rating != null ? Math.round((insights.average_rating / 5) * 100) : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">Review &amp; Reputation</h1>
          <p className="mt-1 text-base text-slate-500">
            Every review is analyzed for sentiment and priority. Responses are always drafted for your review --
            nothing posts anywhere without your approval.
          </p>
        </div>
        <Button size="sm" variant="secondary" loading={importMut.isPending} onClick={() => importMut.mutate()}>
          <Download size={16} className="mr-1" />
          Import sample reviews
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Reputation score" value={reputationScore != null ? `${reputationScore}` : '-'} />
        <StatCard label="Average rating" value={insights?.average_rating != null ? insights.average_rating.toFixed(1) : '-'} />
        <StatCard label="Total reviews" value={String(insights?.review_count ?? 0)} />
        <StatCard label="Positive %" value={insights ? `${insights.sentiment_breakdown.positive ?? 0}%` : '-'} />
        <StatCard label="Negative %" value={insights ? `${insights.sentiment_breakdown.negative ?? 0}%` : '-'} />
        <StatCard label="Needs attention" value={String(insights?.reviews_requiring_attention ?? 0)} />
      </div>

      {insights?.insufficient_data ? (
        <Card>
          <p className="text-sm text-slate-400">
            Not enough analyzed reviews yet for insights. Import sample reviews above, or add one manually below, to
            get started.
          </p>
        </Card>
      ) : (
        <Card title="Insights">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div>
              <p className="text-sm font-medium text-emerald-600">Top positive topics</p>
              <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
                {(insights?.top_positive_topics ?? []).map((t) => (
                  <li key={t.topic}>
                    {t.topic} ({t.count})
                  </li>
                ))}
                {insights?.top_positive_topics.length === 0 && <li className="text-slate-400">None yet</li>}
              </ul>
            </div>
            <div>
              <p className="text-sm font-medium text-red-600">Top negative topics</p>
              <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
                {(insights?.top_negative_topics ?? []).map((t) => (
                  <li key={t.topic}>
                    {t.topic} ({t.count})
                  </li>
                ))}
                {insights?.top_negative_topics.length === 0 && <li className="text-slate-400">None yet</li>}
              </ul>
            </div>
          </div>
          {insights?.summary && <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">{insights.summary}</p>}
          {trends && !trends.insufficient_data && trends.sudden_spike && (
            <p className="mt-3 flex items-center gap-1.5 rounded-xl bg-red-50 p-3 text-sm text-red-700">
              <AlertTriangle size={16} />
              Negative reviews jumped from {trends.previous_negative_pct}% to {trends.current_negative_pct}% over
              the last {trends.current_period_days} days.
              {trends.recurring_negative_topics[0] && ` Most mentioned: ${trends.recurring_negative_topics[0].topic}.`}
            </p>
          )}
        </Card>
      )}

      <Card title="Log a review">
        <div className="flex flex-col gap-2 md:flex-row">
          <input
            type="text"
            value={newReviewText}
            onChange={(e) => setNewReviewText(e.target.value)}
            placeholder="Paste a review's text..."
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-violet-400"
          />
          <input
            type="number"
            min={1}
            max={5}
            value={newReviewRating}
            onChange={(e) => setNewReviewRating(e.target.value)}
            placeholder="Rating (optional)"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-violet-400 md:w-40"
          />
          <Button size="sm" disabled={!newReviewText.trim()} loading={addMut.isPending} onClick={() => addMut.mutate()}>
            <MessageSquare size={16} className="mr-1" />
            Add
          </Button>
        </div>
      </Card>

      <div className="flex flex-wrap gap-2">
        <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm">
          <option value="">All priorities</option>
          {['low', 'medium', 'high', 'critical'].map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select value={sentiment} onChange={(e) => setSentiment(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm">
          <option value="">All sentiments</option>
          {['positive', 'neutral', 'negative', 'mixed'].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2 py-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={attentionOnly} onChange={(e) => setAttentionOnly(e.target.checked)} />
          Needs attention only
        </label>
      </div>

      <div className="space-y-3">
        {reviews.map((review) => (
          <ReviewCard key={review.id} review={review} />
        ))}
        {reviews.length === 0 && (
          <div className="py-12 text-center text-base text-slate-400">No reviews match these filters yet.</div>
        )}
      </div>
    </div>
  )
}

export function ReviewsPage() {
  const { data: plan, isLoading } = usePlan()
  if (isLoading) return null

  if (!plan?.features.review_reputation_enabled) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">Review &amp; Reputation</h1>
        <PlanGate feature="review_reputation_enabled">
          <span />
        </PlanGate>
      </div>
    )
  }

  return <ReviewsPageContent />
}
