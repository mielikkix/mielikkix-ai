import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../shared/api/client'
import { Card } from '../../shared/components/Card'
import { Button } from '../../shared/components/Button'
import { Input } from '../../shared/components/Input'
import { UsageMeter } from '../../shared/components/UsageMeter'
import { usePlan } from '../../shared/hooks/usePlan'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { useT } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

interface Product {
  id: string
  name: string
  description: string | null
  price: number | null
  currency: string
  category: string | null
  is_active: boolean
}

const emptyForm = { name: '', description: '', price: '', currency: 'USD', category: '' }

interface ProductFormFieldsProps {
  form: typeof emptyForm
  onChange: (key: string) => (e: React.ChangeEvent<HTMLInputElement>) => void
  multiCurrencyAllowed: boolean
}

// Defined at module scope, not inside ProductsPage's render body -- a
// component redefined on every render gets a new identity each time, so
// React unmounts/remounts it (and every input inside, losing focus) on
// every keystroke instead of just updating it in place.
function ProductFormFields({ form, onChange, multiCurrencyAllowed }: ProductFormFieldsProps) {
  const { t } = useT()
  return (
    <div className="grid grid-cols-2 gap-3">
      <Input label={t('products.name')} value={form.name} onChange={onChange('name')} className="col-span-2" />
      <Input label={t('products.description')} value={form.description} onChange={onChange('description')} className="col-span-2" />
      <Input label={t('products.price')} type="number" value={form.price} onChange={onChange('price')} />
      <Input
        label={t('products.currency')}
        value={form.currency}
        onChange={onChange('currency')}
        disabled={!multiCurrencyAllowed}
        title={!multiCurrencyAllowed ? t('products.currencyLocked') : undefined}
      />
      <Input label={t('products.category')} value={form.category} onChange={onChange('category')} className="col-span-2" />
    </div>
  )
}

export function ProductsPage() {
  const qc = useQueryClient()
  const { t, formatMoney } = useT()
  const { data: products = [] } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: () => api.get('/products').then((r) => r.data),
  })
  const { data: plan } = usePlan()
  const productLimit = plan?.limits.max_products ?? null
  const atProductLimit = productLimit !== null && products.length >= productLimit
  const multiCurrencyAllowed = !!plan?.features.multi_currency

  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const createMut = useMutation({
    mutationFn: (body: typeof emptyForm) =>
      api.post('/products', { ...body, price: body.price ? parseFloat(body.price) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['products'] }); setAdding(false); setForm(emptyForm) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string } & typeof emptyForm) =>
      api.patch(`/products/${id}`, { ...body, price: body.price ? parseFloat(body.price) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['products'] }); setEditId(null) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/products/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['products'] }),
  })

  const startEdit = (p: Product) => {
    setEditId(p.id)
    setForm({ name: p.name, description: p.description || '', price: p.price?.toString() || '', currency: p.currency, category: p.category || '' })
  }

  // Same bug/fix as FAQsPage's formIncomplete: an empty Save click
  // silently created a nameless product with no error shown -- see
  // schemas/product.py's _not_blank for the backend side of this.
  const formIncomplete = !form.name.trim()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-slate-900">{t('products.title')}</h1>
          <p className="text-base text-slate-500 mt-1">{t('products.subtitle')}</p>
        </div>
        <Button size="sm" disabled={atProductLimit} onClick={() => setAdding(true)}><Plus size={16} className="mr-1" />{t('products.add')}</Button>
      </div>

      <UsageMeter label={t('products.usage')} used={products.length} limit={productLimit} />

      {adding && (
        <Card title={t('products.newTitle')}>
          <div className="space-y-3">
            <ProductFormFields form={form} onChange={set} multiCurrencyAllowed={multiCurrencyAllowed} />
            <div className="flex gap-2">
              <Button size="sm" disabled={formIncomplete} loading={createMut.isPending} onClick={() => createMut.mutate(form)}>{t('common.save')}</Button>
              <Button size="sm" variant="secondary" onClick={() => { setAdding(false); setForm(emptyForm) }}>{t('common.cancel')}</Button>
            </div>
            {createMut.isError && (
              <p role="alert" className="text-sm text-red-600">{apiErrorMessage(createMut.error, 'products.saveFailed')}</p>
            )}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {products.map((p) => (
          <Card key={p.id}>
            {editId === p.id ? (
              <div className="space-y-3">
                <ProductFormFields form={form} onChange={set} multiCurrencyAllowed={multiCurrencyAllowed} />
                <div className="flex gap-2">
                  <Button size="sm" disabled={formIncomplete} loading={updateMut.isPending} onClick={() => updateMut.mutate({ id: p.id, ...form })}>{t('common.save')}</Button>
                  <Button size="sm" variant="secondary" onClick={() => setEditId(null)}>{t('common.cancel')}</Button>
                </div>
                {updateMut.isError && (
                  <p role="alert" className="text-sm text-red-600">{apiErrorMessage(updateMut.error, 'products.saveFailed')}</p>
                )}
              </div>
            ) : (
              <div>
                <div className="flex items-start justify-between">
                  <p className="font-semibold text-slate-900 text-lg">{p.name}</p>
                  <div className="flex gap-1">
                    <button onClick={() => startEdit(p)} aria-label={t('products.editLabel')} title={t('products.editLabel')} className="p-1 rounded hover:bg-slate-100 text-slate-400"><Pencil size={13} /></button>
                    <button onClick={() => deleteMut.mutate(p.id)} aria-label={t('products.deleteLabel')} title={t('products.deleteLabel')} className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500"><Trash2 size={13} /></button>
                  </div>
                </div>
                {p.description && <p className="text-base text-slate-500 mt-1 line-clamp-2">{p.description}</p>}
                {p.price != null && (
                  <p className="mt-2 text-lg font-medium text-brand-600">{formatMoney(Number(p.price), p.currency)}</p>
                )}
                {p.category && <span className="mt-1 inline-block text-sm bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{p.category}</span>}
              </div>
            )}
          </Card>
        ))}
      </div>
      {products.length === 0 && !adding && (
        <div className="text-center py-12 text-slate-400 text-base">{t('products.empty')}</div>
      )}
    </div>
  )
}
