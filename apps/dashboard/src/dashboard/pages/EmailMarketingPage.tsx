import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, Users, RefreshCw } from 'lucide-react'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { PlanGate } from '../../shared/components/PlanGate'
import { usePlan } from '../../shared/hooks/usePlan'

interface MailchimpStatus {
  connected: boolean
  configured: boolean
  account_name?: string | null
  login_email?: string | null
  audience_id?: string | null
  audience_name?: string | null
  connected_at?: string | null
}

interface MailchimpAudience {
  id: string
  name: string
  member_count: number
}

// Only Mailchimp exists today -- see app/integrations/email_marketing_providers/
// __init__.py's PROVIDER_NAMES for the roadmapped ("resend") but not-yet-built
// second provider. This page is intentionally Mailchimp-only for Phase 1;
// a provider picker isn't needed until a second provider actually exists.

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as any)?.response?.data?.detail
  return typeof detail === 'string' && detail ? detail : fallback
}

function AudiencePicker({ selectedId, onSelected }: { selectedId?: string | null; onSelected: () => void }) {
  const {
    data: audiences,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<MailchimpAudience[]>({
    queryKey: ['mailchimp-audiences'],
    queryFn: () => api.get('/businesses/me/mailchimp/audiences').then((r) => r.data),
  })

  const selectMut = useMutation({
    mutationFn: (audience: MailchimpAudience) =>
      api.post('/businesses/me/mailchimp/select-audience', { audience_id: audience.id, name: audience.name }),
    onSuccess: onSelected,
  })

  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading your Mailchimp audiences...</p>
  }

  if (isError) {
    return (
      <div className="space-y-2">
        <p className="text-sm font-medium text-red-600">{errorDetail(error, "Couldn't load audiences from Mailchimp -- please try again.")}</p>
        <Button size="sm" variant="secondary" loading={isFetching} onClick={() => refetch()}>
          <RefreshCw size={14} className="mr-1" />
          Retry
        </Button>
      </div>
    )
  }

  if (!audiences || audiences.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-slate-500">
          No audiences found in this Mailchimp account. Create one in Mailchimp, then refresh below.
        </p>
        <Button size="sm" variant="secondary" loading={isFetching} onClick={() => refetch()}>
          <RefreshCw size={14} className="mr-1" />
          Refresh
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {selectMut.isError && (
        <p className="text-sm font-medium text-red-600">
          {errorDetail(selectMut.error, "Couldn't save your audience selection -- please try again.")}
        </p>
      )}
      {audiences.map((audience) => (
        <div
          key={audience.id}
          className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-3"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-900">{audience.name}</p>
            <p className="flex items-center gap-1 text-xs text-slate-500">
              <Users size={12} />
              {audience.member_count.toLocaleString()} contact{audience.member_count === 1 ? '' : 's'}
            </p>
          </div>
          <Button
            size="sm"
            variant={audience.id === selectedId ? 'secondary' : 'primary'}
            disabled={audience.id === selectedId}
            loading={selectMut.isPending && selectMut.variables?.id === audience.id}
            onClick={() => selectMut.mutate(audience)}
          >
            {audience.id === selectedId ? 'Selected' : 'Select'}
          </Button>
        </div>
      ))}
    </div>
  )
}

function MailchimpConnectionCard() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [banner, setBanner] = useState<'connected' | 'error' | null>(null)
  const [changingAudience, setChangingAudience] = useState(false)
  const [connecting, setConnecting] = useState(false)

  useEffect(() => {
    const value = searchParams.get('mailchimp')
    if (value === 'connected' || value === 'error') {
      setBanner(value)
      qc.invalidateQueries({ queryKey: ['mailchimp-status'] })
      const next = new URLSearchParams(searchParams)
      next.delete('mailchimp')
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { data: status, isLoading } = useQuery<MailchimpStatus>({
    queryKey: ['mailchimp-status'],
    queryFn: () => api.get('/businesses/me/mailchimp/status').then((r) => r.data),
  })

  const disconnectMut = useMutation({
    mutationFn: () => api.delete('/businesses/me/mailchimp'),
    onSuccess: () => {
      setBanner(null)
      setChangingAudience(false)
      qc.invalidateQueries({ queryKey: ['mailchimp-status'] })
    },
  })

  if (isLoading) return null

  if (!status?.configured) {
    return (
      <Card title="Mailchimp">
        <p className="text-sm text-slate-500">
          Mailchimp connection isn't set up for this environment yet. Once it's configured, you'll be able to
          connect your real Mailchimp account here.
        </p>
      </Card>
    )
  }

  if (!status.connected) {
    return (
      <Card title="Mailchimp">
        <div className="space-y-3">
          {banner === 'error' && <p className="text-sm text-red-600">Couldn't connect Mailchimp. Please try again.</p>}
          <p className="text-sm text-slate-500">
            Connect your Mailchimp account to manage your email audience from Mielikkix -- see who's on your list
            and pick which audience your future campaigns will use.
          </p>
          <Button
            size="sm"
            loading={connecting}
            onClick={() => {
              setConnecting(true)
              window.location.href = `${api.defaults.baseURL}/businesses/me/mailchimp/authorize`
            }}
          >
            <Mail size={14} className="mr-1" />
            Connect Mailchimp
          </Button>
        </div>
      </Card>
    )
  }

  const showPicker = changingAudience || !status.audience_id

  return (
    <Card title="Mailchimp">
      <div className="space-y-3">
        {banner === 'connected' && <p className="text-sm text-emerald-600">Mailchimp connected!</p>}
        <p className="text-sm text-slate-700">
          Mailchimp connected{status.account_name ? ` -- ${status.account_name}` : ''}
          {status.login_email ? ` (${status.login_email})` : ''}.
        </p>

        {status.audience_id && !showPicker && (
          <div className="rounded-xl bg-slate-50 px-4 py-3">
            <p className="text-sm font-medium text-slate-900">Selected audience: {status.audience_name || status.audience_id}</p>
          </div>
        )}

        {!showPicker ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => setChangingAudience(true)}>
              Change Audience
            </Button>
            <Button size="sm" variant="danger" loading={disconnectMut.isPending} onClick={() => disconnectMut.mutate()}>
              Disconnect
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium text-slate-500">Choose an audience</p>
            <AudiencePicker selectedId={status.audience_id} onSelected={() => setChangingAudience(false)} />
            <div className="flex flex-wrap gap-2">
              {status.audience_id && (
                <Button size="sm" variant="ghost" onClick={() => setChangingAudience(false)}>
                  Cancel
                </Button>
              )}
              <Button size="sm" variant="danger" loading={disconnectMut.isPending} onClick={() => disconnectMut.mutate()}>
                Disconnect
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

function EmailMarketingPageContent() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold text-slate-900">Email Marketing</h1>
        <p className="mt-1 text-slate-500">
          Connect your email marketing account to manage your audience from Mielikkix.
        </p>
      </div>
      <MailchimpConnectionCard />
    </div>
  )
}

export function EmailMarketingPage() {
  const { data: plan, isLoading } = usePlan()
  if (isLoading) return null

  if (!plan?.features.email_marketing_enabled) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold text-slate-900">Email Marketing</h1>
        <PlanGate feature="email_marketing_enabled">
          <span />
        </PlanGate>
      </div>
    )
  }

  return <EmailMarketingPageContent />
}
