import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Input } from '../../../shared/components/Input'
import { useAuthStore } from '../../../shared/store/authStore'
import { marketingPath, useT, type MessageKey } from '../../../shared/i18n'
import { apiErrorMessage } from '../../../shared/i18n/apiError'

// Settings -> "Privacy & data" (GDPR Phase 4). Self-contained (own queries),
// unlike the chatbot sections above it, since none of this is chatbot config.
// Backed by apps/api/app/api/account.py.

export interface ConsentEntry {
  type: string
  document_version: string | null
  granted: boolean
  granted_at: string
  withdrawn_at: string | null
  source: string
}

export interface PrivacyState {
  business_name: string
  marketing_emails: boolean
  pending_acceptance: string[]
  deletion_requested_at: string | null
  deletion_scheduled_for: string | null
  is_owner: boolean
  history: ConsentEntry[]
}

// Consent types/sources are stored codes (consent_service.py); only the labels are translated.
const TYPE_LABELS: Record<string, MessageKey> = {
  terms: 'settings.privacy.types.terms',
  dpa: 'settings.privacy.types.dpa',
  age_confirmation: 'settings.privacy.types.age_confirmation',
  marketing_email: 'settings.privacy.types.marketing_email',
}

const SOURCE_LABELS: Record<string, MessageKey> = {
  register: 'settings.privacy.sources.register',
  settings: 'settings.privacy.sources.settings',
  unsubscribe: 'settings.privacy.sources.unsubscribe',
  reaccept: 'settings.privacy.sources.reaccept',
}

export function PrivacySection() {
  const qc = useQueryClient()
  const { t, locale, formatDate } = useT()
  const longDate = (iso: string) => formatDate(iso, 'long')
  // The legal documents exist in both languages on mielikkix.ai.
  const legal = { terms: marketingPath(locale, '/terms/'), dpa: marketingPath(locale, '/dpa/'), privacy: marketingPath(locale, '/privacy/') }
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const { data, isLoading } = useQuery<PrivacyState>({
    queryKey: ['account-privacy'],
    queryFn: () => api.get('/account/privacy').then((r) => r.data),
  })

  const onChanged = (next: PrivacyState) => {
    qc.setQueryData(['account-privacy'], next)
    void checkAuth() // refresh the deletion banner in the layout
  }

  const marketingMut = useMutation({
    mutationFn: (subscribed: boolean) => api.put('/account/marketing', { subscribed }).then((r) => r.data),
    onSuccess: onChanged,
  })

  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const exportData = async () => {
    setExporting(true)
    setExportError('')
    try {
      const resp = await api.get('/account/export', { responseType: 'blob' })
      const url = URL.createObjectURL(resp.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `mielikkix-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setExportError(t('settings.privacy.exportFailed'))
    } finally {
      setExporting(false)
    }
  }

  const [confirmName, setConfirmName] = useState('')
  const deleteMut = useMutation({
    mutationFn: () => api.post('/account/deletion', { confirm_business_name: confirmName }).then((r) => r.data),
    onSuccess: (next: PrivacyState) => {
      setConfirmName('')
      onChanged(next)
    },
  })
  const cancelMut = useMutation({
    mutationFn: () => api.delete('/account/deletion').then((r) => r.data),
    onSuccess: onChanged,
  })

  if (isLoading || !data) return <p className="text-base text-slate-500">{t('settings.privacy.loading')}</p>

  return (
    <div className="space-y-6">
      <Card title={t('settings.privacy.exportTitle')}>
        <p className="text-base text-slate-600">
          {t('settings.privacy.exportText')}
          {data.is_owner && t('settings.privacy.exportOwnerExtra')}
          {t('settings.privacy.exportEnd')}
        </p>
        <Button className="mt-4" variant="secondary" loading={exporting} onClick={exportData}>
          {t('settings.privacy.exportButton')}
        </Button>
        {exportError && <p role="alert" className="mt-2 text-sm text-red-500">{exportError}</p>}
      </Card>

      <Card title={t('settings.privacy.emailTitle')}>
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-brand-600"
            // Optimistic: show the new state while it saves (reverts on error).
            checked={marketingMut.isPending ? !!marketingMut.variables : data.marketing_emails}
            disabled={marketingMut.isPending}
            onChange={(e) => marketingMut.mutate(e.target.checked)}
          />
          <span className="text-base text-slate-700">
            {t('settings.privacy.marketing')}
            <span className="block text-sm text-slate-500">{t('settings.privacy.marketingHelp')}</span>
          </span>
        </label>
        {marketingMut.isError && <p role="alert" className="mt-2 text-sm text-red-500">{t('settings.privacy.saveFailed')}</p>}
      </Card>

      <Card title={t('settings.privacy.agreementsTitle')}>
        <p className="text-sm text-slate-500 mb-3">
          {t('settings.privacy.agreementsBefore')}
          <a className="text-brand-600 underline" href={legal.terms} target="_blank" rel="noopener noreferrer">{t('settings.privacy.terms')}</a>
          {t('settings.privacy.comma')}
          <a className="text-brand-600 underline" href={legal.dpa} target="_blank" rel="noopener noreferrer">{t('settings.privacy.dpa')}</a>
          {t('settings.privacy.and')}
          <a className="text-brand-600 underline" href={legal.privacy} target="_blank" rel="noopener noreferrer">{t('settings.privacy.privacyPolicy')}</a>
          {t('settings.privacy.agreementsAfter')}
        </p>
        {data.history.length === 0 ? (
          <p className="text-base text-slate-500">{t('settings.privacy.noRecords')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-2 pr-4 font-medium">{t('settings.privacy.columns.item')}</th>
                  <th className="py-2 pr-4 font-medium">{t('settings.privacy.columns.choice')}</th>
                  <th className="py-2 pr-4 font-medium">{t('settings.privacy.columns.date')}</th>
                  <th className="py-2 font-medium">{t('settings.privacy.columns.via')}</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((h, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top">
                    <td className="py-2 pr-4 text-slate-800">
                      {TYPE_LABELS[h.type] ? t(TYPE_LABELS[h.type]) : h.type}
                      {h.document_version && <span className="block text-xs text-slate-400">{h.document_version}</span>}
                    </td>
                    <td className="py-2 pr-4">
                      {h.granted
                        ? h.withdrawn_at
                          ? t('settings.privacy.withdrawn')
                          : t('settings.privacy.given')
                        : t('settings.privacy.declined')}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">{longDate(h.granted_at)}</td>
                    <td className="py-2">{SOURCE_LABELS[h.source] ? t(SOURCE_LABELS[h.source]) : h.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data.is_owner && (
        <Card title={t('settings.privacy.deleteTitle')}>
          {data.deletion_scheduled_for ? (
            <div className="space-y-3">
              <p className="text-base text-slate-700">
                {t('settings.privacy.scheduled', { date: longDate(data.deletion_scheduled_for) })}
              </p>
              <Button variant="secondary" loading={cancelMut.isPending} onClick={() => cancelMut.mutate()}>
                {t('settings.privacy.cancelDeletion')}
              </Button>
              {cancelMut.isError && <p role="alert" className="text-sm text-red-500">{apiErrorMessage(cancelMut.error, 'settings.privacy.cancelFailed')}</p>}
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault()
                deleteMut.mutate()
              }}
            >
              <p className="text-base text-slate-700">
                {t('settings.privacy.deleteTextBefore')}
                <strong>{t('settings.privacy.deleteGrace')}</strong>
                {t('settings.privacy.deleteTextMiddle')}
                <a className="text-brand-600 underline" href={legal.privacy} target="_blank" rel="noopener noreferrer">{t('settings.privacy.privacyPolicyLink')}</a>
                {t('settings.privacy.deleteTextAfter')}
              </p>
              <Input
                label={t('settings.privacy.confirmLabel', { name: data.business_name })}
                value={confirmName}
                onChange={(e) => setConfirmName(e.target.value)}
                autoComplete="off"
              />
              <Button
                type="submit"
                variant="danger"
                loading={deleteMut.isPending}
                disabled={confirmName.trim() !== data.business_name.trim()}
              >
                {t('settings.privacy.deleteButton')}
              </Button>
              {deleteMut.isError && <p role="alert" className="text-sm text-red-500">{apiErrorMessage(deleteMut.error, 'settings.privacy.deleteFailed')}</p>}
            </form>
          )}
        </Card>
      )}
    </div>
  )
}
