import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, ChevronRight, ChevronLeft, ExternalLink } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { articleStateLabel } from './articleStatus'

interface ArticleAuthor {
  id: string
  full_name: string
  email: string
}

interface Article {
  id: string
  title: string
  slug: string
  status: 'draft' | 'published'
  deployment_status: 'not_deployed' | 'pending' | 'live' | 'failed'
  last_deployment_error: string | null
  author: ArticleAuthor
  published_at: string | null
  updated_at: string
}

interface ArticleListOut {
  items: Article[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 20

const TABS = [
  { key: 'all', label: 'All', status: undefined },
  { key: 'drafts', label: 'Drafts', status: 'draft' },
  { key: 'published', label: 'Published', status: 'published' },
] as const

// MielikkiX Admin -> Articles. Platform-admin-only (this whole page lives
// under RequireAdmin in App.tsx, and every API call it makes is gated
// server-side by require_platform_admin too -- see app/api/
// admin_articles.py -- so hiding this nav item is a UX nicety here, never
// the actual security boundary).
export function AdminArticlesPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<(typeof TABS)[number]['key']>('all')
  const [page, setPage] = useState(1)

  const activeTab = TABS.find((t) => t.key === tab)!

  const { data, isLoading } = useQuery<ArticleListOut>({
    queryKey: ['admin', 'articles', activeTab.status, page],
    queryFn: () =>
      api
        .get('/admin/articles', { params: { status: activeTab.status, page, page_size: PAGE_SIZE } })
        .then((r) => r.data),
    placeholderData: (prev) => prev,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'articles'] })

  const publishMut = useMutation({
    mutationFn: (id: string) => api.post(`/admin/articles/${id}/publish`),
    onSuccess: invalidate,
  })

  const unpublishMut = useMutation({
    mutationFn: (id: string) => api.post(`/admin/articles/${id}/unpublish`),
    onSuccess: invalidate,
  })

  const deploymentResultMut = useMutation({
    mutationFn: ({ id, success, message }: { id: string; success: boolean; message?: string }) =>
      api.post(`/admin/articles/${id}/deployment-result`, { success, message }),
    onSuccess: invalidate,
  })

  const markDeployed = (id: string) => {
    if (confirm('Confirm that you just built and deployed the website, and this article is now live on mielikkix.ai?')) {
      deploymentResultMut.mutate({ id, success: true })
    }
  }

  const reportDeploymentFailed = (id: string) => {
    const message = window.prompt('What went wrong with the deployment? (shown to other admins on this article)')
    if (message !== null) {
      deploymentResultMut.mutate({ id, success: false, message: message || undefined })
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">Articles</h1>
          <p className="text-base text-slate-500 mt-1">
            Create and publish articles for the Mielikkix website's blog (mielikkix.ai/blog). Website deployment is
            manual for now -- Publish saves to the database; a platform admin still needs to build and deploy the
            site, then confirm it below.
          </p>
        </div>
        <Link to="/admin/articles/new">
          <Button size="sm">
            <Plus size={16} className="mr-1" /> Create Article
          </Button>
        </Link>
      </div>

      <div className="flex gap-2 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => {
              setTab(t.key)
              setPage(1)
            }}
            className={clsx(
              'px-4 py-2 text-base font-medium border-b-2 -mb-px',
              tab === t.key ? 'border-brand-600 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-700'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-base">
            <thead>
              <tr className="border-b border-slate-100 text-sm text-slate-500">
                <th className="px-6 py-3 font-medium">Title</th>
                <th className="px-6 py-3 font-medium">Slug</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Published</th>
                <th className="px-6 py-3 font-medium">Updated</th>
                <th className="px-6 py-3 font-medium">Author</th>
                <th className="px-6 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((article) => {
                const state = articleStateLabel(article)
                const needsDeploymentAction = article.status === 'published' && article.deployment_status !== 'live'
                return (
                  <tr key={article.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                    <td className="px-6 py-4 font-semibold text-slate-900">
                      <Link to={`/admin/articles/${article.id}/edit`} className="hover:text-brand-600">
                        {article.title}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-500">/{article.slug}</td>
                    <td className="px-6 py-4">
                      <span
                        className={clsx('rounded-full px-2.5 py-1 text-xs font-semibold', state.className)}
                        title={article.last_deployment_error ?? undefined}
                      >
                        {state.label}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-500">
                      {article.published_at ? new Date(article.published_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-500">{new Date(article.updated_at).toLocaleDateString()}</td>
                    <td className="px-6 py-4 text-sm text-slate-500">{article.author.full_name}</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={`/admin/articles/${article.id}/edit`} className="text-sm font-semibold text-brand-600 hover:underline">
                          Edit
                        </Link>
                        {article.status === 'draft' ? (
                          <Button size="sm" variant="secondary" loading={publishMut.isPending} onClick={() => publishMut.mutate(article.id)}>
                            Publish
                          </Button>
                        ) : (
                          <Button size="sm" variant="secondary" loading={unpublishMut.isPending} onClick={() => unpublishMut.mutate(article.id)}>
                            Unpublish
                          </Button>
                        )}
                        {needsDeploymentAction && (
                          <>
                            <Button size="sm" variant="secondary" loading={deploymentResultMut.isPending} onClick={() => markDeployed(article.id)}>
                              Mark as Deployed
                            </Button>
                            <Button size="sm" variant="ghost" loading={deploymentResultMut.isPending} onClick={() => reportDeploymentFailed(article.id)}>
                              Report Failed
                            </Button>
                          </>
                        )}
                        {article.status === 'published' && article.deployment_status === 'live' && (
                          <a
                            href={`https://mielikkix.ai/blog/${article.slug}/`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-slate-600"
                            title="View live"
                          >
                            <ExternalLink size={16} />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
              {!isLoading && data && data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-400">
                    No articles yet. Create the first one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-base text-slate-500">
          <span>
            Page {data.page} of {totalPages} · {data.total} articles
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50"
            >
              <ChevronLeft size={16} /> Prev
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50"
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
