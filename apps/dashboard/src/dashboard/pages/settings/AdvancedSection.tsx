import { UseMutationResult } from '@tanstack/react-query'
import { Card } from '../../../shared/components/Card'
import { Button } from '../../../shared/components/Button'
import { Input } from '../../../shared/components/Input'
import { Settings, FieldChangeEvent } from './types'

interface Props {
  form: Partial<Settings>
  set: (k: keyof Settings) => (e: FieldChangeEvent) => void
  advancedMut: UseMutationResult<unknown, unknown, void>
}

const RETENTION_OPTIONS = [7, 30, 90, 180, 365]

export function AdvancedSection({ form, set, advancedMut }: Props) {
  return (
    <div className="space-y-6">
      <Card title="Contact info">
        <div className="space-y-3">
          <Input label="Contact email" type="email" value={form.contact_email || ''} onChange={set('contact_email')} />
          <Input label="Contact phone" value={form.contact_phone || ''} onChange={set('contact_phone')} />
        </div>
      </Card>

      {/* GDPR Phase 5: you are the controller for your visitors' data; these
          drive the widget's AI notice link and the nightly deletion job. */}
      <Card title="Visitor privacy">
        <div className="space-y-4">
          <Input
            label="Your privacy policy URL"
            type="url"
            placeholder="https://yourbusiness.com/privacy"
            value={form.privacy_policy_url || ''}
            onChange={set('privacy_policy_url')}
          />
          <p className="-mt-2 text-sm text-slate-500">
            Linked from the chat widget's "you're chatting with an AI assistant" notice. Mention the widget in your
            privacy and cookie notices: it stores a session ID in the visitor's browser (sessionStorage) only once they
            open the chat.
          </p>
          <div>
            <label htmlFor="retention" className="block text-base font-medium text-slate-700 mb-1">
              Delete visitor conversations after
            </label>
            <select
              id="retention"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
              value={String(form.conversation_retention_days ?? 90)}
              onChange={set('conversation_retention_days')}
            >
              {RETENTION_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d} days{d === 90 ? ' (default)' : ''}
                </option>
              ))}
            </select>
            <p className="mt-1 text-sm text-slate-500">
              Counted from the conversation's last message. Leads you've captured are kept. Maximum 365 days.
            </p>
          </div>
        </div>
      </Card>

      <Card title="AI Provider">
        <div className="space-y-3">
          <div>
            <label className="block text-base font-medium text-slate-700 mb-1">LLM Provider</label>
            <select
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
            label="Model name (optional)"
            value={form.llm_model || ''}
            onChange={set('llm_model')}
            placeholder="e.g. openai/gpt-oss-120b — leave blank to use the default"
          />
        </div>
      </Card>

      <Button loading={advancedMut.isPending} onClick={() => advancedMut.mutate()}>
        Save advanced settings
      </Button>
      {advancedMut.isSuccess && <p className="text-base text-green-600">Advanced settings saved!</p>}
      {advancedMut.isError && (
        <p role="alert" className="text-base text-red-500">
          {(advancedMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Couldn't save. Please check the fields above."}
        </p>
      )}
    </div>
  )
}
