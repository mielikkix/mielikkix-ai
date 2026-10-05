import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { Button } from '../../shared/components/Button'
import { marketingPath, useT, type MessageKey } from '../../shared/i18n'
import { queryClient } from '../../shared/queryClient'
import { useAuthStore } from '../../shared/store/authStore'

// GDPR Phase 4 notices shown on every dashboard page (DashboardLayout):
//  - a blocking modal while the user hasn't accepted the current Terms/DPA
//    (the API also refuses everything but /auth and /account routes until
//    they do -- core/dependencies.py), and
//  - a banner while the account is scheduled for deletion.

// The legal pages exist in both languages on mielikkix.ai; the Norwegian copy is under /no/.
const DOC_LINKS: Record<string, { label: MessageKey; path: string }> = {
  terms: { label: 'notices.reaccept.documents.terms', path: '/terms/' },
  dpa: { label: 'notices.reaccept.documents.dpa', path: '/dpa/' },
}

function ReacceptanceModal({ documents }: { documents: string[] }) {
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const logout = useAuthStore((s) => s.logout)
  const [agreed, setAgreed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const { t, locale } = useT()
  const docLabel = (d: string) => (DOC_LINKS[d] ? t(DOC_LINKS[d].label) : d)

  const accept = async () => {
    setSaving(true)
    setError('')
    try {
      await api.post('/account/consents/accept', { documents })
      await checkAuth()
      // Queries that failed with 403 while acceptance was pending.
      await queryClient.invalidateQueries()
    } catch {
      setError(t('notices.reaccept.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby="reaccept-title" className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 id="reaccept-title" className="text-xl font-bold text-slate-900">{t('notices.reaccept.title')}</h2>
        <p className="mt-2 text-base text-slate-600">{t('notices.reaccept.intro')}</p>
        <ul className="mt-3 list-disc pl-5 text-base">
          {documents.map((d) => (
            <li key={d}>
              <a
                href={DOC_LINKS[d] ? marketingPath(locale, DOC_LINKS[d].path) : undefined}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-600 underline"
              >
                {docLabel(d)}
              </a>
            </li>
          ))}
        </ul>
        <label className="mt-4 flex items-start gap-3 text-sm text-slate-700">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-brand-600" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          {t('notices.reaccept.agree', { documents: documents.map(docLabel).join(t('notices.reaccept.and')) })}
        </label>
        {error && <p role="alert" className="mt-2 text-sm text-red-500">{error}</p>}
        <div className="mt-5 flex flex-wrap gap-2">
          <Button disabled={!agreed} loading={saving} onClick={accept}>{t('notices.reaccept.accept')}</Button>
          <Button variant="ghost" onClick={() => void logout()}>{t('notices.reaccept.signOut')}</Button>
        </div>
        <p className="mt-4 text-sm text-slate-500">
          {t('notices.reaccept.disagreeBefore')}
          <Link to="/dashboard/settings?tab=privacy" className="text-brand-600 underline">{t('notices.reaccept.disagreeLink')}</Link>
          {t('notices.reaccept.disagreeAfter')}
        </p>
      </div>
    </div>
  )
}

function DeletionBanner({ scheduledFor }: { scheduledFor: string }) {
  const { t, formatDate } = useT()
  return (
    <div role="status" className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 md:px-8">
      <strong>{t('notices.deletion.scheduled', { date: formatDate(scheduledFor, 'long') })}</strong>{' '}
      <Link to="/dashboard/settings?tab=privacy" className="font-semibold underline">{t('notices.deletion.cancel')}</Link>
    </div>
  )
}

export function AccountNotices() {
  const user = useAuthStore((s) => s.user)
  const location = useLocation()
  if (!user) return null
  const pending = user.pending_acceptance ?? []
  // The modal steps aside on the privacy settings tab, so export/delete stay usable without agreeing.
  const onPrivacyTab = location.pathname === '/dashboard/settings' && new URLSearchParams(location.search).get('tab') === 'privacy'
  return (
    <>
      {user.deletion_scheduled_for && <DeletionBanner scheduledFor={user.deletion_scheduled_for} />}
      {pending.length > 0 && !onPrivacyTab && <ReacceptanceModal documents={pending} />}
    </>
  )
}
