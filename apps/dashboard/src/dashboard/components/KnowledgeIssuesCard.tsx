import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { api } from '../../shared/api/client'
import { useT } from '../../shared/i18n'

interface Issue {
  kind: 'similar_faqs' | 'product_price_mismatch' | string
  message: string
  items: Record<string, string | null>[]
}

/**
 * QA 2026-10-02 (E9, D7): warns when the knowledge base contradicts itself -- two FAQs asking
 * the same question with different answers, or one product listed at two prices -- so the
 * chatbot doesn't pick one at random. Renders nothing when everything agrees.
 */
export function KnowledgeIssuesCard() {
  const { t } = useT()
  const { data: issues = [] } = useQuery<Issue[]>({
    queryKey: ['faqs', 'issues'],
    queryFn: () => api.get('/faqs/issues').then((r) => r.data),
  })
  if (issues.length === 0) return null
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <p className="flex items-center gap-2 font-semibold text-amber-800">
        <AlertTriangle size={16} /> {t('knowledge.title', { count: issues.length })}
      </p>
      <ul className="mt-2 space-y-3 text-sm text-amber-900">
        {issues.map((issue, i) => (
          <li key={i}>
            {/* The API's explanation is English; the two known kinds are explained here instead. */}
            <p>
              {issue.kind === 'similar_faqs'
                ? t('knowledge.similarFaqs')
                : issue.kind === 'product_price_mismatch'
                  ? t('knowledge.priceMismatch')
                  : issue.message}
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-amber-800">
              {issue.items.map((item, j) =>
                issue.kind === 'similar_faqs' ? (
                  <li key={j}>
                    <span className="font-medium">{item.question}</span> {'\u2192'} {item.answer}
                  </li>
                ) : (
                  <li key={j}>
                    {item.name}: {item.price ?? t('knowledge.noPrice')} {item.currency ?? ''}
                  </li>
                )
              )}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  )
}
