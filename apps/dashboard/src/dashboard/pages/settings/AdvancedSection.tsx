import { UseMutationResult } from '@tanstack/react-query'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Input } from '../../../shared/components/Input'
import { Settings, FieldChangeEvent } from './types'
import { useT } from '../../../shared/i18n'
import { apiErrorMessage } from '../../../shared/i18n/apiError'

interface Props {
  form: Partial<Settings>
  set: (k: keyof Settings) => (e: FieldChangeEvent) => void
  advancedMut: UseMutationResult<unknown, unknown, void>
  /** The AI provider/model choice is shown to the platform operator only. */
  isPlatformAdmin: boolean
  /** The plan's conversation history (null = no plan cap); retention choices stop there. */
  maxRetentionDays: number | null
}

const RETENTION_OPTIONS = [7, 30, 90, 180, 365]

export function AdvancedSection({ form, set, advancedMut, isPlatformAdmin, maxRetentionDays }: Props) {
  const { t } = useT()
  // QA 2026-10-02 (M5): every plan could pick up to 365 days, though Free keeps 7 days of history and
  // Start 90. An existing longer setting stays selectable (and is kept) until it's changed.
  const current = Number(form.conversation_retention_days ?? 90)
  const allowed = RETENTION_OPTIONS.filter((d) => maxRetentionDays == null || d <= maxRetentionDays)
  const retentionOptions = allowed.includes(current) ? allowed : [...allowed, current].sort((a, b) => a - b)
  return (
    <div className="space-y-6">
      <Card title={t('settings.advanced.contactTitle')}>
        <div className="space-y-3">
          <p className="text-sm text-slate-500">{t('settings.advanced.contactHelp')}</p>
          <Input label={t('settings.advanced.contactEmail')} type="email" value={form.contact_email || ''} onChange={set('contact_email')} />
          <Input label={t('settings.advanced.contactPhone')} value={form.contact_phone || ''} onChange={set('contact_phone')} />
        </div>
      </Card>

      {/* GDPR Phase 5: you are the controller for your visitors' data; these
          drive the widget's AI notice link and the nightly deletion job. */}
      <Card title={t('settings.advanced.privacyTitle')}>
        <div className="space-y-4">
          <Input
            label={t('settings.advanced.privacyUrl')}
            type="url"
            placeholder={t('settings.advanced.privacyUrlPlaceholder')}
            value={form.privacy_policy_url || ''}
            onChange={set('privacy_policy_url')}
          />
          <p className="-mt-2 text-sm text-slate-500">{t('settings.advanced.privacyHelp')}</p>
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 rounded border-slate-300"
              checked={!!form.require_chat_consent}
              onChange={set('require_chat_consent')}
            />
            <span>
              <span className="block text-base font-medium text-slate-700">{t('settings.advanced.consent')}</span>
              <span className="block text-sm text-slate-500">{t('settings.advanced.consentHelp')}</span>
            </span>
          </label>
          <div>
            <label htmlFor="retention" className="block text-base font-medium text-slate-700 mb-1">
              {t('settings.advanced.retention')}
            </label>
            <select
              id="retention"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              value={String(form.conversation_retention_days ?? 90)}
              onChange={set('conversation_retention_days')}
            >
              {retentionOptions.map((d) => (
                <option key={d} value={d}>
                  {t('settings.advanced.days', { count: d })}
                  {maxRetentionDays != null && d > maxRetentionDays ? ` ${t('settings.advanced.beyondPlan')}` : ''}
                </option>
              ))}
            </select>
            <p className="mt-1 text-sm text-slate-500">
              {t('settings.advanced.retentionHelp')}
              {maxRetentionDays != null && ` ${t('settings.advanced.retentionPlan', { days: maxRetentionDays })}`}
            </p>
          </div>
        </div>
      </Card>

      {isPlatformAdmin && (
      <Card title={t('settings.advanced.aiTitle')}>
        <div className="space-y-3">
          <div>
            <label htmlFor="settings-llm-provider" className="block text-base font-medium text-slate-700 mb-1">{t('settings.advanced.provider')}</label>
            <select
              id="settings-llm-provider"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              value={form.llm_provider || 'groq'}
              onChange={set('llm_provider')}
            >
              {['groq', 'gemini', 'ollama'].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <Input
            label={t('settings.advanced.model')}
            value={form.llm_model || ''}
            onChange={set('llm_model')}
            placeholder={t('settings.advanced.modelPlaceholder')}
          />
        </div>
      </Card>
      )}

      <Button loading={advancedMut.isPending} onClick={() => advancedMut.mutate()}>
        {t('settings.advanced.save')}
      </Button>
      {advancedMut.isSuccess && <p role="status" className="text-base text-green-600">{t('settings.advanced.saved')}</p>}
      {advancedMut.isError && (
        <p role="alert" className="text-base text-red-500">
          {apiErrorMessage(advancedMut.error, 'settings.advanced.saveFailed')}
        </p>
      )}
    </div>
  )
}
