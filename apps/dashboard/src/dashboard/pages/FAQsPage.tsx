import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { Pencil, Trash2, Plus, Check, X } from 'lucide-react'

interface FAQ {
  id: string
  question: string
  answer: string
  category: string | null
  is_active: boolean
}

export function FAQsPage() {
  const qc = useQueryClient()
  const { data: faqs = [] } = useQuery<FAQ[]>({
    queryKey: ['faqs'],
    queryFn: () => api.get('/faqs').then((r) => r.data),
  })

  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ question: '', answer: '', category: '' })

  const createMut = useMutation({
    mutationFn: (body: typeof form) => api.post('/faqs', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['faqs'] }); setAdding(false); setForm({ question: '', answer: '', category: '' }) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string } & typeof form) => api.patch(`/faqs/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['faqs'] }); setEditId(null) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/faqs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['faqs'] }),
  })

  const startEdit = (faq: FAQ) => {
    setEditId(faq.id)
    setForm({ question: faq.question, answer: faq.answer, category: faq.category || '' })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">FAQs</h1>
          <p className="text-base text-slate-500 mt-1">Manage frequently asked questions for your chatbot.</p>
        </div>
        <Button onClick={() => setAdding(true)} size="sm">
          <Plus size={16} className="mr-1" /> Add FAQ
        </Button>
      </div>

      {adding && (
        <Card title="New FAQ">
          <div className="space-y-3">
            <Input label="Question" value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} />
            <div>
              <label className="block text-base font-medium text-slate-700 mb-1">Answer</label>
              <textarea className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" rows={3}
                value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} />
            </div>
            <Input label="Category (optional)" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
            <div className="flex gap-2">
              <Button size="sm" loading={createMut.isPending} onClick={() => createMut.mutate(form)}>Save</Button>
              <Button size="sm" variant="secondary" onClick={() => setAdding(false)}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}

      <div className="space-y-3">
        {faqs.map((faq) => (
          <Card key={faq.id}>
            {editId === faq.id ? (
              <div className="space-y-3">
                <Input value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} />
                <textarea className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" rows={3}
                  value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} />
                <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category" />
                <div className="flex gap-2">
                  <Button size="sm" loading={updateMut.isPending} onClick={() => updateMut.mutate({ id: faq.id, ...form })}>
                    <Check size={14} className="mr-1" /> Save
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setEditId(null)}>
                    <X size={14} className="mr-1" /> Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-900 text-lg">{faq.question}</p>
                  <p className="text-base text-slate-600 mt-1">{faq.answer}</p>
                  {faq.category && (
                    <span className="mt-2 inline-block text-sm bg-brand-50 text-brand-700 px-2 py-0.5 rounded-full">{faq.category}</span>
                  )}
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  <button onClick={() => startEdit(faq)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => deleteMut.mutate(faq.id)} className="p-1.5 rounded hover:bg-red-50 text-slate-500 hover:text-red-600">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            )}
          </Card>
        ))}
        {faqs.length === 0 && !adding && (
          <div className="text-center py-12 text-slate-400 text-base">No FAQs yet. Add your first one above.</div>
        )}
      </div>
    </div>
  )
}
