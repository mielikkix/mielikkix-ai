// Shared between AdminArticlesPage and AdminArticleFormPage -- a single
// combined label so "published" is never shown as if it means "live".
// Deployment is manual for now (2026-09-20 decision): Publish only ever
// changes the database, so an article sits at "Pending Deployment" until
// a platform admin manually builds/uploads the site and then reports the
// result back via POST .../deployment-result (see app/api/
// admin_articles.py and app/services/article_service.py's own docstring).
export interface ArticleStatusFields {
  status: 'draft' | 'published'
  deployment_status: 'not_deployed' | 'pending' | 'live' | 'failed'
}

export interface ArticleStateLabel {
  label: string
  className: string
}

export function articleStateLabel(article: ArticleStatusFields): ArticleStateLabel {
  if (article.status === 'draft') {
    return { label: 'Draft', className: 'bg-slate-100 text-slate-600' }
  }
  if (article.deployment_status === 'live') {
    return { label: 'Published — Live', className: 'bg-emerald-50 text-emerald-700' }
  }
  if (article.deployment_status === 'failed') {
    return { label: 'Published — Deployment Failed', className: 'bg-red-50 text-red-700' }
  }
  // "pending" or "not_deployed" -- both mean "not confirmed live yet"
  return { label: 'Published — Pending Deployment', className: 'bg-amber-50 text-amber-700' }
}
