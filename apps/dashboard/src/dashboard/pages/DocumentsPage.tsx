import { useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { UsageMeter } from '../../shared/components/UsageMeter'
import { usePlan } from '../../shared/hooks/usePlan'
import { Upload, Trash2, FileText, Link2, Globe, Loader2, CheckCircle, AlertCircle, AlertTriangle, RefreshCw } from 'lucide-react'
import { t as translateNow, useT, type MessageKey } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'
import { olderVersions } from './documentVersions'

interface Doc {
  id: string
  filename: string
  file_url: string
  file_type: string
  status: string
  created_at: string
  title: string | null
  char_count: number | null
}

// QA 2026-10-02 (E6): show what each document is, when it was added and how much text it gave.
function textSize(chars: number | null, formatNumber: (n: number, digits?: number) => string): string | null {
  if (chars == null) return null
  if (chars < 1000) return translateNow('documents.chars', { count: formatNumber(chars) })
  return translateNow('documents.charsK', { count: formatNumber(chars / 1000, chars < 10000 ? 1 : 0) })
}

const STATUS_LABELS: Record<string, MessageKey> = {
  embedded: 'documents.status.embedded',
  processing: 'documents.status.processing',
  failed: 'documents.status.failed',
}

const statusIcon = (status: string) => {
  if (status === 'embedded') return <CheckCircle size={14} className="text-green-500" />
  if (status === 'failed') return <AlertCircle size={14} className="text-red-500" />
  return <Loader2 size={14} className="text-slate-400 animate-spin" />
}

export function DocumentsPage() {
  const qc = useQueryClient()
  const { t, formatDate, formatNumber } = useT()
  const fileRef = useRef<HTMLInputElement>(null)
  const [url, setUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [siteUrl, setSiteUrl] = useState('')
  const [siteError, setSiteError] = useState('')
  const [siteMessage, setSiteMessage] = useState('')
  const [siteExclude, setSiteExclude] = useState('')
  // A crawl's first page can finish (and its Document row appear) before
  // our very next poll -- if that poll is also the first one, the query's
  // cached data won't show a "processing" row yet, so the "is anything
  // processing" check alone can end polling before it ever started. Force
  // polling for a window after triggering a crawl, independent of that check.
  const [crawlPollUntil, setCrawlPollUntil] = useState(0)

  const { data: docs = [] } = useQuery<Doc[]>({
    queryKey: ['documents'],
    queryFn: () => api.get('/documents').then((r) => r.data),
    // Crawled pages appear/complete asynchronously in the background, unlike
    // a single upload or single-page fetch which resolves in the same
    // request -- poll while anything is still processing so the list
    // updates itself instead of needing a manual refresh.
    refetchInterval: (query) => {
      const stillProcessing = query.state.data?.some((d) => d.status === 'processing')
      return stillProcessing || Date.now() < crawlPollUntil ? 3000 : false
    },
    // A whole-site crawl can run for a while -- keep polling even if the
    // owner tabs away and back before it finishes, not just while this tab
    // stays focused the entire time.
    refetchIntervalInBackground: true,
  })
  const { data: plan } = usePlan()
  const docLimit = plan?.limits.max_document_uploads ?? null
  const atDocLimit = docLimit !== null && docs.length >= docLimit
  const older = useMemo(() => olderVersions(docs), [docs])

  const uploadMut = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return api.post('/documents', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  const urlMut = useMutation({
    mutationFn: (url: string) => api.post('/documents/from-url', { url }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      setUrl('')
      setUrlError('')
    },
    onError: (err: unknown) => setUrlError(apiErrorMessage(err, 'documents.page.failed')),
  })

  const siteMut = useMutation({
    mutationFn: (url: string) =>
      api
        .post('/documents/from-website', {
          url,
          exclude: siteExclude.split(/[\n,]/).map((s) => s.trim()).filter(Boolean),
        })
        .then((r) => r.data),
    onSuccess: (data: { discovered: number; queued: number; message: string }) => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      // Keep polling for a while regardless of what this immediate refetch
      // sees -- the background crawl may not have written its first row yet.
      setCrawlPollUntil(Date.now() + 30000)
      setSiteUrl('')
      setSiteError('')
      // Rebuilt from the counts so it follows the UI language (data.message is English).
      setSiteMessage(translateNow('documents.site.started', { count: data.queued }))
    },
    onError: (err: unknown) => {
      setSiteError(apiErrorMessage(err, 'documents.site.failed'))
      setSiteMessage('')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/documents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  const refetchMut = useMutation({
    mutationFn: (id: string) => api.post(`/documents/${id}/refetch`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMut.mutate(file)
    e.target.value = ''
  }

  const handleFetchUrl = () => {
    if (!url.trim()) return
    setUrlError('')
    urlMut.mutate(url.trim())
  }

  const handleImportSite = () => {
    if (!siteUrl.trim()) return
    setSiteError('')
    setSiteMessage('')
    siteMut.mutate(siteUrl.trim())
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">{t('documents.title')}</h1>
          <p className="text-base text-slate-500 mt-1">{t('documents.subtitle')}</p>
        </div>
        <Button size="sm" loading={uploadMut.isPending} disabled={atDocLimit} onClick={() => fileRef.current?.click()}>
          <Upload size={16} className="mr-1" /> {t('documents.upload')}
        </Button>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.csv,.xlsx" className="hidden" onChange={handleFile} />
      </div>

      <UsageMeter label={t('documents.usage')} used={docs.length} limit={docLimit} />
      {uploadMut.isError && (
        <p role="alert" className="text-sm text-red-600">{apiErrorMessage(uploadMut.error, 'documents.uploadFailed')}</p>
      )}

      <Card title={t('documents.page.title')}>
        <p className="text-base text-slate-500 mb-3">{t('documents.page.intro')}</p>
        <div className="flex gap-2">
          <div className="flex-1">
            <Input
              placeholder={t('documents.page.placeholder')}
              aria-label={t('documents.page.label')}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleFetchUrl()}
            />
          </div>
          <Button size="sm" loading={urlMut.isPending} onClick={handleFetchUrl}>
            <Link2 size={16} className="mr-1" /> {t('documents.page.fetch')}
          </Button>
        </div>
        {urlError && <p role="alert" className="text-sm text-red-500 mt-2">{urlError}</p>}
      </Card>

      <Card title={t('documents.site.title')}>
        <p className="text-base text-slate-500 mb-3">{t('documents.site.intro')}</p>
        <div className="flex gap-2">
          <div className="flex-1">
            <Input
              placeholder={t('documents.site.placeholder')}
              aria-label={t('documents.site.label')}
              value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleImportSite()}
            />
          </div>
          <Button size="sm" loading={siteMut.isPending} onClick={handleImportSite}>
            <Globe size={16} className="mr-1" /> {t('documents.site.import')}
          </Button>
        </div>
        <div className="mt-2">
          <Input
            placeholder={t('documents.site.excludePlaceholder')}
            aria-label={t('documents.site.excludeLabel')}
            value={siteExclude}
            onChange={(e) => setSiteExclude(e.target.value)}
          />
        </div>
        {siteError && <p role="alert" className="text-sm text-red-500 mt-2">{siteError}</p>}
        {siteMessage && <p role="status" className="text-sm text-emerald-600 mt-2">{siteMessage}</p>}
      </Card>

      <div className="space-y-3">
        {older.size > 0 && (
          <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
            <span>{t('documents.olderVersions', { count: older.size })}</span>
          </div>
        )}
        {docs.map((doc) => {
          const isPage = doc.file_type === 'url'
          const size = textSize(doc.char_count, formatNumber)
          return (
            <Card key={doc.id}>
              <div className="flex items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  {isPage ? <Globe size={20} className="flex-shrink-0 text-slate-400" /> : <FileText size={20} className="flex-shrink-0 text-slate-400" />}
                  <div className="min-w-0">
                    <p className="truncate text-lg font-medium text-slate-900">{doc.title || doc.filename}</p>
                    {isPage && (
                      <a href={doc.file_url} target="_blank" rel="noopener noreferrer" className="block truncate text-sm text-brand-600 hover:underline">
                        {doc.filename}
                      </a>
                    )}
                    <div className="flex flex-wrap items-center gap-1.5 mt-0.5 text-sm text-slate-500">
                      {statusIcon(doc.status)}
                      <span>{STATUS_LABELS[doc.status] ? t(STATUS_LABELS[doc.status]) : doc.status}</span>
                      <span>· {t('documents.added', { date: formatDate(doc.created_at) })}</span>
                      {size && <span>· {size}</span>}
                    </div>
                    {older.has(doc.id) && (
                      <p className="mt-1 flex items-center gap-1 text-sm font-medium text-amber-700">
                        <AlertTriangle size={13} aria-hidden="true" /> {t('documents.olderVersionOf', { name: older.get(doc.id)! })}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-1">
                  {isPage && (
                    <button
                      onClick={() => refetchMut.mutate(doc.id)}
                      disabled={refetchMut.isPending && refetchMut.variables === doc.id}
                      className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-50"
                      title={t('documents.refetchTitle')}
                    >
                      <RefreshCw size={13} className={refetchMut.isPending && refetchMut.variables === doc.id ? 'animate-spin' : ''} /> {t('documents.refetch')}
                    </button>
                  )}
                  <button
                    onClick={() => confirm(t('documents.deleteConfirm', { name: doc.title || doc.filename })) && deleteMut.mutate(doc.id)}
                    className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                    aria-label={t('documents.delete')}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </Card>
          )
        })}
        {refetchMut.isError && <p role="alert" className="text-sm text-red-600">{t('documents.refetchFailed')}</p>}
        {docs.length === 0 && (
          <div className="text-center py-12 text-slate-400 text-base">{t('documents.empty')}</div>
        )}
      </div>
    </div>
  )
}
