import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'
import { useT } from '../../shared/i18n'
import { apiErrorMessage } from '../../shared/i18n/apiError'

export function ForgotPasswordPage() {
  const { t } = useT()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await api.post('/auth/forgot-password', { email })
      setSubmitted(true)
    } catch (err: unknown) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="text-4xl font-bold text-slate-900 mb-1">{t('auth.forgot.title')}</h1>

      {submitted ? (
        <>
          <p className="text-base text-slate-500 mb-4">
            {t('auth.forgot.sentBefore')}
            <strong className="text-slate-700">{email}</strong>
            {t('auth.forgot.sentAfter')}
          </p>
          <p className="text-base text-slate-500">{t('auth.forgot.checkInbox')}</p>
          <button
            type="button"
            onClick={() => setSubmitted(false)}
            className="mt-4 text-sm text-brand-600 hover:underline"
          >
            {t('auth.forgot.tryAgain')}
          </button>
        </>
      ) : (
        <>
          <p className="text-base text-slate-500 mb-6">{t('auth.forgot.intro')}</p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input label={t('auth.forgot.email')} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
            <Button type="submit" loading={loading} className="w-full">{t('auth.forgot.submit')}</Button>
          </form>
        </>
      )}

      <p className="mt-4 text-center text-base text-slate-500">
        <Link to="/login" className="text-brand-600 font-medium hover:underline">
          {t('auth.forgot.backToLogin')}
        </Link>
      </p>
    </AuthLayout>
  )
}
