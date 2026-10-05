import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'
import { useT } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

export function ResetPasswordPage() {
  const navigate = useNavigate()
  const { t } = useT()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirmPassword) {
      setError(t('auth.reset.mismatch'))
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/reset-password', { token, new_password: password })
      navigate('/login')
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'auth.reset.invalidLink'))
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <AuthLayout contentClassName="text-center">
        <h1 className="text-2xl font-bold text-slate-900 mb-2">{t('auth.reset.missingTitle')}</h1>
        <p className="text-base text-slate-500 mb-4">{t('auth.reset.missingText')}</p>
        <Link to="/forgot-password" className="text-brand-600 font-medium hover:underline">
          {t('auth.reset.requestNew')}
        </Link>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <h1 className="text-4xl font-bold text-slate-900 mb-1">{t('auth.reset.title')}</h1>
      <p className="text-base text-slate-500 mb-6">{t('auth.reset.intro')}</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label={t('auth.reset.newPassword')}
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Input
          label={t('auth.reset.confirmPassword')}
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
        />
        {error && (
          <p role="alert" className="text-sm text-red-500">
            {error}{' '}
            <Link to="/forgot-password" className="underline">{t('auth.reset.requestNew')}</Link>
          </p>
        )}
        <Button type="submit" loading={loading} className="w-full">{t('auth.reset.submit')}</Button>
      </form>
    </AuthLayout>
  )
}
