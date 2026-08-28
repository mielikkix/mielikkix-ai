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

export function AdvancedSection({ form, set, advancedMut }: Props) {
  return (
    <div className="space-y-6">
      <Card title="Contact info">
        <div className="space-y-3">
          <Input label="Contact email" type="email" value={form.contact_email || ''} onChange={set('contact_email')} />
          <Input label="Contact phone" value={form.contact_phone || ''} onChange={set('contact_phone')} />
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
    </div>
  )
}
