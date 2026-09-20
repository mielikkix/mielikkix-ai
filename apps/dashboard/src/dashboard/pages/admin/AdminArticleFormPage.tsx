import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, TriangleAlert } from 'lucide-react'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Input } from '../../../shared/components/Input'
import { articleStateLabel } from './articleStatus'

interface Article {
  id: string
  title: string
  slug: string
  excerpt: string | null
  content: string
  status: 'draft' | 'published'
  deployment_status: 'not_deployed' | 'pending' | 'live' | 'failed'
  last_deployment_error: string | null
  last_deployed_at: string | null
  featured_image_url: string | null
  meta_title: string | null
  meta_description: string | null
  canonical_url: string | null
  keywords: string[]
  category: string | null
  tags: string[]
}

interface FormState {
  title: string
  slug: string
  excerpt: string
  content: string
  featured_image_url: string
  meta_title: string
  meta_description: string
  canonical_url: string
  keywords: string
  category: string
  tags: string
}

const BLANK_FORM: FormState = {
  title: '',
  slug: '',
  excerpt: '',
  content: '',
  featured_image_url: '',
  meta_title: '',
  meta_description: '',
  canonical_url: '',
  keywords: '',
  category: '',
  tags: '',
}

function articleToForm(article: Article): FormState {
  return {
    title: article.title,
    slug: article.slug,
    excerpt: article.excerpt ?? '',
    content: article.content,
    featured_image_url: article.featured_image_url ?? '',
    meta_title: article.meta_title ?? '',
    meta_description: article.meta_description ?? '',
    canonical_url: article.canonical_url ?? '',
    keywords: article.keywords.join(', '),
    category: article.category ?? '',
    tags: article.tags.join(', '),
  }
}

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
}

// Handles BOTH /admin/articles/new and /admin/articles/:id/edit -- one
// component, since every field is identical between create and edit (see
// this feature's own spec: "Use existing UI components" / avoid a second
// near-duplicate form). Publishing/unpublishing lives on this page too
// (rather than only on the list) so an admin editing a draft can publish
// the exact version they just saved without a round trip back to the list.
export function AdminArticleFormPage() {
  const { id } = useParams<{ id: string }>()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [form, setForm] = useState<FormState>(BLANK_FORM)

  const { data: article, isLoading } = useQuery<Article>({
    queryKey: ['admin', 'articles', id],
    queryFn: () => api.get(`/admin/articles/${id}`).then((r) => r.data),
    enabled: isEdit,
  })

  useEffect(() => {
    if (article) {
      setForm(articleToForm(article))
    }
  }, [article])

  const set = (field: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }))

  const buildPayload = () => ({
    title: form.title,
    slug: form.slug || undefined,
    excerpt: form.excerpt || null,
    content: form.content,
    featured_image_url: form.featured_image_url || null,
    meta_title: form.meta_title || null,
    meta_description: form.meta_description || null,
    canonical_url: form.canonical_url || null,
    keywords: splitList(form.keywords),
    category: form.category || null,
    tags: splitList(form.tags),
  })

  const createMut = useMutation({
    mutationFn: () => api.post('/admin/articles', buildPayload()),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ['admin', 'articles'] })
      navigate(`/admin/articles/${resp.data.id}/edit`)
    },
  })

  const updateMut = useMutation({
    mutationFn: () => api.patch(`/admin/articles/${id}`, buildPayload()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'articles', id] }),
  })

  const publishMut = useMutation({
    mutationFn: () => api.post(`/admin/articles/${id}/publish`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'articles', id] }),
  })

  const unpublishMut = useMutation({
    mutationFn: () => api.post(`/admin/articles/${id}/unpublish`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'articles', id] }),
  })

  const deploymentResultMut = useMutation({
    mutationFn: (body: { success: boolean; message?: string }) => api.post(`/admin/articles/${id}/deployment-result`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'articles', id] }),
  })

  const markDeployed = () => {
    if (confirm('Confirm that you just built and deployed the website, and this article is now live on mielikkix.ai?')) {
      deploymentResultMut.mutate({ success: true })
    }
  }

  const reportDeploymentFailed = () => {
    const message = window.prompt('What went wrong with the deployment?')
    if (message !== null) {
      deploymentResultMut.mutate({ success: false, message: message || undefined })
    }
  }

  // Permanent deletion (DELETE /api/admin/articles/{id}) -- a real database
  // delete, never a status change (see article_service.delete_article's own
  // docstring). Deliberately its own confirmation dialog, not window.confirm
  // like the deployment actions above: this is the one truly irreversible
  // action on this page, so it gets the fuller "here's exactly what you're
  // deleting" treatment the feature spec asked for.
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const deleteMut = useMutation({
    mutationFn: () => api.delete(`/admin/articles/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'articles'] })
      navigate('/admin/articles')
    },
  })

  const confirmDelete = () => {
    if (deleteMut.isPending) return
    deleteMut.mutate()
  }

  const saveError = (createMut.error ?? updateMut.error) as any
  const deleteError = deleteMut.error as any
  const formIncomplete = !form.title.trim() || !form.content.trim()

  if (isEdit && isLoading) return <p className="text-slate-400">Loading…</p>

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <Link to="/admin/articles" className="text-slate-400 hover:text-slate-600">
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-slate-900">{isEdit ? 'Edit Article' : 'Create Article'}</h1>
          {article && (
            <span
              className={`mt-1 inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${articleStateLabel(article).className}`}
            >
              {articleStateLabel(article).label}
            </span>
          )}
        </div>
      </div>

      {isEdit && article?.status === 'published' && (
        <Card title="Deployment">
          <div className="space-y-3 text-base">
            <p className="text-slate-700">
              Website deployment is manual -- publishing only saves this article to the database. Build and deploy
              the site yourself, then confirm the result here so this article's status reflects reality.
            </p>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-slate-400">Article status</dt>
                <dd className="font-medium text-slate-800">{article.status}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Deployment status</dt>
                <dd className="font-medium text-slate-800">{article.deployment_status.replace('_', ' ')}</dd>
              </div>
              <div>
                <dt className="text-slate-400">Last deployed</dt>
                <dd className="font-medium text-slate-800">
                  {article.last_deployed_at ? new Date(article.last_deployed_at).toLocaleString() : '—'}
                </dd>
              </div>
            </dl>
            {article.last_deployment_error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{article.last_deployment_error}</p>
            )}
            {article.deployment_status !== 'live' && (
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="secondary" loading={deploymentResultMut.isPending} onClick={markDeployed}>
                  Mark as Deployed
                </Button>
                <Button size="sm" variant="ghost" loading={deploymentResultMut.isPending} onClick={reportDeploymentFailed}>
                  Report Deployment Failed
                </Button>
              </div>
            )}
          </div>
        </Card>
      )}

      <Card>
        <div className="space-y-4">
          <Input label="Title" value={form.title} onChange={set('title')} />
          <Input
            label="Slug"
            value={form.slug}
            placeholder="auto-generated from title if left blank"
            onChange={set('slug')}
          />
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">Excerpt</label>
            <textarea
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              rows={2}
              value={form.excerpt}
              onChange={set('excerpt')}
            />
          </div>
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">Content (HTML)</label>
            <textarea
              className="w-full rounded-xl border border-slate-300 px-3 py-2 font-mono text-sm"
              rows={16}
              value={form.content}
              onChange={set('content')}
            />
            <p className="mt-1 text-sm text-slate-400">
              Sanitized server-side on save (a safe subset of HTML tags -- scripts and inline event handlers are always stripped).
            </p>
          </div>
          <Input label="Featured image URL" value={form.featured_image_url} onChange={set('featured_image_url')} />
        </div>
      </Card>

      <Card title="SEO">
        <div className="space-y-4">
          <Input label="Meta title" value={form.meta_title} placeholder="Falls back to the title" onChange={set('meta_title')} />
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">Meta description</label>
            <textarea
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              rows={2}
              placeholder="Falls back to the excerpt"
              value={form.meta_description}
              onChange={set('meta_description')}
            />
          </div>
          <Input
            label="Canonical URL (optional)"
            value={form.canonical_url}
            placeholder={`Defaults to https://mielikkix.ai/blog/${form.slug || '<slug>'}/`}
            onChange={set('canonical_url')}
          />
          <Input label="Category" value={form.category} onChange={set('category')} />
          <Input label="Keywords (comma-separated)" value={form.keywords} onChange={set('keywords')} />
          <Input label="Tags (comma-separated)" value={form.tags} onChange={set('tags')} />
        </div>
      </Card>

      {saveError && (
        <p className="text-sm text-red-600">{saveError?.response?.data?.detail ?? 'Could not save this article.'}</p>
      )}

      <div className="flex items-center gap-3">
        <Button
          disabled={formIncomplete}
          loading={createMut.isPending || updateMut.isPending}
          onClick={() => (isEdit ? updateMut.mutate() : createMut.mutate())}
        >
          {isEdit ? 'Save Changes' : 'Save Draft'}
        </Button>

        {isEdit && article?.status === 'draft' && (
          <Button variant="secondary" loading={publishMut.isPending} onClick={() => publishMut.mutate()}>
            Publish
          </Button>
        )}
        {isEdit && article?.status === 'published' && (
          <>
            <Button variant="secondary" loading={unpublishMut.isPending} onClick={() => unpublishMut.mutate()}>
              Unpublish
            </Button>
            {article.deployment_status === 'live' && (
              <a
                href={`https://mielikkix.ai/blog/${article.slug}/`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:underline"
              >
                View live <ExternalLink size={14} />
              </a>
            )}
          </>
        )}
      </div>

      {isEdit && article && (
        <Card title="Danger Zone" className="border-red-200">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-slate-500">
              Permanently delete this article from the database. This cannot be undone from the dashboard.
            </p>
            <Button variant="danger" size="sm" onClick={() => setConfirmingDelete(true)}>
              Delete Article
            </Button>
          </div>
        </Card>
      )}

      {confirmingDelete && article && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="flex items-start gap-3">
              <TriangleAlert className="mt-0.5 flex-shrink-0 text-red-600" size={22} />
              <div>
                <h2 className="text-lg font-bold text-slate-900">Delete Article?</h2>
                <p className="mt-2 text-sm text-slate-600">You are about to permanently delete:</p>
                <p className="mt-1 font-semibold text-slate-900">{article.title}</p>
                <p className="mt-1 text-sm text-slate-500">
                  Slug: <code className="rounded bg-slate-100 px-1 py-0.5">/blog/{article.slug}/</code>
                </p>
                <p className="mt-3 text-sm text-slate-600">
                  This action cannot be undone. The article will be removed from the database and will not be
                  included in future website builds.
                </p>
              </div>
            </div>

            {deleteError && (
              <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {deleteError?.response?.data?.detail ?? 'Could not delete this article.'}
              </p>
            )}

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" disabled={deleteMut.isPending} onClick={() => setConfirmingDelete(false)}>
                Cancel
              </Button>
              <Button variant="danger" loading={deleteMut.isPending} onClick={confirmDelete}>
                Delete Permanently
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
