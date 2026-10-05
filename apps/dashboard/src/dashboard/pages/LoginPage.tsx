import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../shared/store/authStore'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'
import { useT } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

export function LoginPage() {
  const navigate = useNavigate()
  const { t } = useT()
  const login = useAuthStore((s) => s.login)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err) {
      setError(apiErrorMessage(err, 'auth.login.invalid'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="text-4xl font-bold text-slate-900 mb-1">{t('auth.login.title')}</h1>
      <p className="text-base text-slate-500 mb-6">{t('auth.login.subtitle')}</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label={t('auth.login.email')} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <div>
          <Input
            label={t('auth.login.password')}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Link to="/forgot-password" className="mt-1 inline-block text-sm text-brand-600 hover:underline">
            {t('auth.login.forgot')}
          </Link>
        </div>
        {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">{t('auth.login.submit')}</Button>
      </form>
      <p className="mt-4 text-center text-base text-slate-500">
        {t('auth.login.noAccount')}{' '}
        <Link to="/register" className="text-brand-600 font-medium hover:underline">
          {t('auth.login.register')}
        </Link>
      </p>
    </AuthLayout>
  )
}
