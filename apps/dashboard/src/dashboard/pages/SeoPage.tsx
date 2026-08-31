import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Check, X } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { PlanGate } from '../../shared/components/PlanGate'
import { usePlan } from '../../shared/hooks/usePlan'

interface Product {
  id: string
  name: string
  description: string | null
  seo_title: string | null
  meta_description: string | null
}

interface SeoDraft {
  id: string
  product_id: string
  draft_description: string
  draft_seo_title: string
  draft_meta_description: string
  status: 'draft' | 'approved' | 'rejected'
}

// Only ever "generate for products I picked, review, approve/reject" -- see
// apps/agents/seo-copywriter/CLAUDE.md: silently overwriting live product
// copy without a review step is the one failure mode this agent must never
// have, so nothing here ever calls PATCH /products directly.
function DraftReview({ product, draft }: { product: Product; draft: SeoDraft }) {
  const qc = useQueryClient()

  const approveMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/drafts/${draft.id}/approve`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo', 'drafts'] })
      qc.invalidateQueries({ queryKey: ['products'] })
    },
  })
  const rejectMut = useMutation({
    mutationFn: () => api.post(`/agents/seo/drafts/${draft.id}/reject`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo', 'drafts'] }),
  })

  return (
    <Card>
      <p className="font-semibold text-slate-900 text-lg">{product.name}</p>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <p className="text-sm font-medium text-slate-400 uppercase tracking-wide">Live now</p>
          <p className="mt-1 text-base text-slate-600">{product.description || '(no description)'}</p>
          <p className="mt-2 text-sm text-slate-400">SEO title: {product.seo_title || '-'}</p>
          <p className="text-sm text-slate-400">Meta: {product.meta_description || '-'}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-brand-600 uppercase tracking-wide">Draft</p>
          <p className="mt-1 text-base text-slate-900">{draft.draft_description}</p>
          <p className="mt-2 text-sm text-slate-600">SEO title: {draft.draft_seo_title}</p>
          <p className="text-sm text-slate-600">Meta: {draft.draft_meta_description}</p>
        </div>
      </div>

      <div className="mt-4 flex gap-2">
        <Button size="sm" loading={approveMut.isPending} onClick={() => approveMut.mutate()}>
          <Check size={16} className="mr-1" />
          Approve
        </Button>
        <Button size="sm" variant="secondary" loading={rejectMut.isPending} onClick={() => rejectMut.mutate()}>
          <X size={16} className="mr-1" />
          Reject
        </Button>
      </div>
    </Card>
  )
}

function SeoPageContent() {
  const qc = useQueryClient()
  const { data: products = [] } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products').then((r) => r.data),
  })
  const { data: drafts = [] } = useQuery<SeoDraft[]>({
    queryKey: ['seo', 'drafts', 'draft'],
    queryFn: () => api.get('/agents/seo/drafts', { params: { status: 'draft' } }).then((r) => r.data),
  })

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const generateMut = useMutation({
    mutationFn: () => api.post('/agents/seo/drafts/generate', { product_ids: [...selected] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo', 'drafts'] })
      setSelected(new Set())
    },
  })

  const productById = new Map(products.map((p) => [p.id, p]))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">SEO Copywriter</h1>
        <p className="text-base text-slate-500 mt-1">
          Generate improved product descriptions and search metadata, and review them before anything
          goes live.
        </p>
      </div>

      <Card title="Pick products to (re)generate">
        <div className="space-y-2">
          {products.map((p) => (
            <label key={p.id} className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => toggle(p.id)}
                className="h-4 w-4 rounded border-slate-300"
              />
              <span className="text-base text-slate-700">{p.name}</span>
            </label>
          ))}
          {products.length === 0 && <p className="text-base text-slate-400">Add products first.</p>}
        </div>
        <Button
          className="mt-4"
          size="sm"
          disabled={selected.size === 0}
          loading={generateMut.isPending}
          onClick={() => generateMut.mutate()}
        >
          <Sparkles size={16} className="mr-1" />
          Generate drafts ({selected.size})
        </Button>
        {generateMut.isError && (
          <p className="mt-2 text-sm text-red-600">Something went wrong generating drafts. Please try again.</p>
        )}
      </Card>

      <div className="space-y-4">
        {drafts.map((draft) => {
          const product = productById.get(draft.product_id)
          if (!product) return null
          return <DraftReview key={draft.id} product={product} draft={draft} />
        })}
        {drafts.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">
            No drafts waiting for review. Pick some products above and generate a batch.
          </div>
        )}
      </div>
    </div>
  )
}

export function SeoPage() {
  const { data: plan, isLoading } = usePlan()
  if (isLoading) return null

  if (!plan?.features.seo_copywriter_enabled) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">SEO Copywriter</h1>
        <PlanGate feature="seo_copywriter_enabled">
          <span />
        </PlanGate>
      </div>
    )
  }

  return <SeoPageContent />
}
