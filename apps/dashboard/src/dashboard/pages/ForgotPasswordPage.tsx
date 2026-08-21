import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'

export function ForgotPasswordPage() {
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
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Something went wrong. Please try again in a moment.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="text-4xl font-bold text-slate-900 mb-1">Forgot password?</h1>

      {submitted ? (
        <>
          <p className="text-base text-slate-500 mb-4">
            If an account exists for <strong className="text-slate-700">{email}</strong>, we've sent a link to reset your password.
          </p>
          <p className="text-base text-slate-500">
            Check your inbox (and spam folder, just in case) — the link is valid for 1 hour.
          </p>
          <button
            type="button"
            onClick={() => setSubmitted(false)}
            className="mt-4 text-sm text-brand-600 hover:underline"
          >
            Didn't get it? Try another email
          </button>
        </>
      ) : (
        <>
          <p className="text-base text-slate-500 mb-6">Enter your email and we'll send you a link to reset it.</p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {error && <p className="text-sm text-red-500">{error}</p>}
            <Button type="submit" loading={loading} className="w-full">Send reset link</Button>
          </form>
        </>
      )}

      <p className="mt-4 text-center text-base text-slate-500">
        <Link to="/login" className="text-brand-600 font-medium hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
