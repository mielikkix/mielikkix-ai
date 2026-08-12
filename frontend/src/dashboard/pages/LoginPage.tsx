import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../shared/store/authStore'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'

export function LoginPage() {
  const navigate = useNavigate()
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
    } catch {
      setError('Invalid email or password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="text-4xl font-bold text-slate-900 mb-1">Welcome back</h1>
      <p className="text-base text-slate-500 mb-6">Sign in to your MielikkiX dashboard</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <div>
          <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <Link to="/forgot-password" className="mt-1 inline-block text-sm text-brand-600 hover:underline">
            Forgot password?
          </Link>
        </div>
        {error && <p className="text-sm text-red-500">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">Sign in</Button>
      </form>
      <p className="mt-4 text-center text-base text-slate-500">
        No account?{' '}
        <Link to="/register" className="text-brand-600 font-medium hover:underline">
          Register
        </Link>
      </p>
    </AuthLayout>
  )
}
