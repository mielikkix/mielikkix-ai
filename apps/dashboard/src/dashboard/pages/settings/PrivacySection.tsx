import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../shared/api/client'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Input } from '../../../shared/components/Input'
import { LEGAL_URLS } from '../../../shared/legal'
import { useAuthStore } from '../../../shared/store/authStore'

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

const TYPE_LABELS: Record<string, string> = {
  terms: 'Terms of Service',
  dpa: 'Data Processing Agreement',
  age_confirmation: '18+ and business sign-up',
  marketing_email: 'Product update emails',
}

const SOURCE_LABELS: Record<string, string> = {
  register: 'Sign-up',
  settings: 'Settings',
  unsubscribe: 'Unsubscribe link',
  reaccept: 'Accepted update',
}

const errorText = (err: unknown, fallback: string) =>
  (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })

export function PrivacySection() {
  const qc = useQueryClient()
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
      setExportError('Export failed. Please try again.')
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

  if (isLoading || !data) return <p className="text-base text-slate-500">Loading…</p>

  return (
    <div className="space-y-6">
      <Card title="Export your data">
        <p className="text-base text-slate-600">
          Download a copy of your account's data as a JSON file: your profile, business settings, consent history
          {data.is_owner && ', and your chatbot data (FAQs, conversations, leads, documents and more)'}.
        </p>
        <Button className="mt-4" variant="secondary" loading={exporting} onClick={exportData}>
          Download my data
        </Button>
        {exportError && <p role="alert" className="mt-2 text-sm text-red-500">{exportError}</p>}
      </Card>

      <Card title="Email preferences">
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
            Send me product updates and tips by email.
            <span className="block text-sm text-slate-500">
              Account emails such as password resets and lead or booking notifications are always sent.
            </span>
          </span>
        </label>
        {marketingMut.isError && <p role="alert" className="mt-2 text-sm text-red-500">Couldn't save. Please try again.</p>}
      </Card>

      <Card title="Your agreements and consents">
        <p className="text-sm text-slate-500 mb-3">
          What you agreed to and when. Read the current <a className="text-brand-600 underline" href={LEGAL_URLS.terms} target="_blank" rel="noopener noreferrer">Terms</a>,{' '}
          <a className="text-brand-600 underline" href={LEGAL_URLS.dpa} target="_blank" rel="noopener noreferrer">DPA</a> and{' '}
          <a className="text-brand-600 underline" href={LEGAL_URLS.privacy} target="_blank" rel="noopener noreferrer">Privacy Policy</a>.
        </p>
        {data.history.length === 0 ? (
          <p className="text-base text-slate-500">No records yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-2 pr-4 font-medium">Item</th>
                  <th className="py-2 pr-4 font-medium">Choice</th>
                  <th className="py-2 pr-4 font-medium">Date</th>
                  <th className="py-2 font-medium">Via</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((h, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top">
                    <td className="py-2 pr-4 text-slate-800">
                      {TYPE_LABELS[h.type] ?? h.type}
                      {h.document_version && <span className="block text-xs text-slate-400">{h.document_version}</span>}
                    </td>
                    <td className="py-2 pr-4">{h.granted ? (h.withdrawn_at ? 'Given, later withdrawn' : 'Given') : 'Declined'}</td>
                    <td className="py-2 pr-4 whitespace-nowrap">{formatDate(h.granted_at)}</td>
                    <td className="py-2">{SOURCE_LABELS[h.source] ?? h.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data.is_owner && (
        <Card title="Delete account">
          {data.deletion_scheduled_for ? (
            <div className="space-y-3">
              <p className="text-base text-slate-700">
                Your account is scheduled for permanent deletion on{' '}
                <strong>{formatDate(data.deletion_scheduled_for)}</strong>. Until then everything keeps working and you can
                cancel.
              </p>
              <Button variant="secondary" loading={cancelMut.isPending} onClick={() => cancelMut.mutate()}>
                Cancel deletion
              </Button>
              {cancelMut.isError && <p role="alert" className="text-sm text-red-500">{errorText(cancelMut.error, "Couldn't cancel. Please try again.")}</p>}
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
                This permanently deletes your business, all users, chatbot data, conversations, leads, documents and
                connected integrations after a <strong>30-day</strong> grace period, during which you can cancel. We keep
                only a minimised record of your agreements and consent choices for 3 years, as described in our{' '}
                <a className="text-brand-600 underline" href={LEGAL_URLS.privacy} target="_blank" rel="noopener noreferrer">Privacy Policy</a>.
                Download your data first if you want a copy.
              </p>
              <Input
                label={`Type your business name (${data.business_name}) to confirm`}
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
                Delete my account
              </Button>
              {deleteMut.isError && <p role="alert" className="text-sm text-red-500">{errorText(deleteMut.error, "Couldn't schedule deletion.")}</p>}
            </form>
          )}
        </Card>
      )}
    </div>
  )
}
