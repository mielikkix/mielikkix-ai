import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { api } from '../../shared/api/client'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'

export function ResetPasswordPage() {
  const navigate = useNavigate()
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
      setError("Passwords don't match.")
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/reset-password', { token, new_password: password })
      navigate('/login')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'That reset link is invalid or has expired.')
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <AuthLayout contentClassName="text-center">
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Invalid reset link</h1>
        <p className="text-base text-slate-500 mb-4">This link is missing its reset token.</p>
        <Link to="/forgot-password" className="text-brand-600 font-medium hover:underline">
          Request a new link
        </Link>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <h1 className="text-4xl font-bold text-slate-900 mb-1">Set a new password</h1>
      <p className="text-base text-slate-500 mb-6">Choose a new password for your account.</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label="New password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Input label="Confirm new password" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
        {error && (
          <p className="text-sm text-red-500">
            {error}{' '}
            <Link to="/forgot-password" className="underline">Request a new link</Link>
          </p>
        )}
        <Button type="submit" loading={loading} className="w-full">Reset password</Button>
      </form>
    </AuthLayout>
  )
}
