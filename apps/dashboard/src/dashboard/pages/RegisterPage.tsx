import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../shared/store/authStore'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'
import { countryOptions, guessCountry } from '../../shared/countries'
import { LEGAL_URLS } from '../../shared/legal'

// GDPR Phase 3. The two required boxes and the marketing box all start
// unticked; the API independently rejects a registration without
// terms_accepted/age_confirmed (apps/api/app/schemas/auth.py), so this form
// is not the only gate.
function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-600 font-medium underline">
      {children}
    </a>
  )
}

function Checkbox({ id, checked, onChange, required, children }: {
  id: string
  checked: boolean
  onChange: (checked: boolean) => void
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        required={required}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 h-4 w-4 shrink-0 accent-brand-600"
      />
      <label htmlFor={id} className="text-sm text-slate-700">{children}</label>
    </div>
  )
}

export function RegisterPage() {
  const navigate = useNavigate()
  const register = useAuthStore((s) => s.register)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const countries = useMemo(() => countryOptions(), [])
  const [form, setForm] = useState({
    business_name: '', business_slug: '', industry: 'retail',
    full_name: '', email: '', password: '', country: guessCountry(),
  })
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [ageConfirmed, setAgeConfirmed] = useState(false)
  const [marketingOptIn, setMarketingOptIn] = useState(false)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    // Browsers already block submit via the checkboxes' `required`; this
    // covers any that don't, with an explicit message.
    if (!termsAccepted || !ageConfirmed) {
      setError('Please accept the Terms of Service and Data Processing Agreement, and confirm you are 18 or older and signing up for a business.')
      return
    }
    if (!form.country) {
      setError('Please select your country.')
      return
    }
    setLoading(true)
    setError('')
    try {
      await register({
        ...form,
        terms_accepted: termsAccepted,
        age_confirmed: ageConfirmed,
        marketing_opt_in: marketingOptIn,
      })
      navigate('/dashboard')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Registration failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout cardClassName="max-w-md">
      <h1 className="text-4xl font-bold text-slate-900 mb-1">Create your account</h1>
      <p className="text-base text-slate-500 mb-6">Start your free Mielikkix trial today</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label="Business name" value={form.business_name} onChange={set('business_name')} required />
        <Input label="Business slug (URL-friendly)" value={form.business_slug} onChange={set('business_slug')} placeholder="my-shop" required />
        <div>
          <label className="block text-base font-medium text-slate-700 mb-1">Industry</label>
          <select className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base" value={form.industry} onChange={set('industry')}>
            {['retail', 'restaurant', 'clinic', 'real_estate', 'service', 'other'].map((i) => (
              <option key={i} value={i}>{i.replace('_', ' ')}</option>
            ))}
          </select>
        </div>
        <Input label="Your name" value={form.full_name} onChange={set('full_name')} required />
        <Input label="Email" type="email" value={form.email} onChange={set('email')} required />
        <Input label="Password" type="password" value={form.password} onChange={set('password')} required />
        <div>
          <label htmlFor="register-country" className="block text-base font-medium text-slate-700 mb-1">Country</label>
          <select
            id="register-country"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.country}
            onChange={set('country')}
            required
          >
            <option value="" disabled>Select your country</option>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
        </div>
        <fieldset className="space-y-3 pt-1">
          <legend className="sr-only">Agreements</legend>
          <Checkbox id="register-terms" checked={termsAccepted} onChange={setTermsAccepted} required>
            I agree to the <ExternalLink href={LEGAL_URLS.terms}>Terms of Service</ExternalLink> and{' '}
            <ExternalLink href={LEGAL_URLS.dpa}>Data Processing Agreement</ExternalLink>.
          </Checkbox>
          <Checkbox id="register-age" checked={ageConfirmed} onChange={setAgeConfirmed} required>
            I confirm I am 18 or older and signing up on behalf of a business.
          </Checkbox>
          <Checkbox id="register-marketing" checked={marketingOptIn} onChange={setMarketingOptIn}>
            Send me product updates and tips by email. You can unsubscribe anytime. (Optional)
          </Checkbox>
        </fieldset>
        {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">Create account</Button>
        <p className="text-sm text-slate-500">
          We process your account data to provide the service. Read our{' '}
          <ExternalLink href={LEGAL_URLS.privacy}>Privacy Policy</ExternalLink>.
        </p>
      </form>
      <p className="mt-4 text-center text-base text-slate-500">
        Already have an account?{' '}
        <Link to="/login" className="text-brand-600 font-medium hover:underline">Sign in</Link>
      </p>
    </AuthLayout>
  )
}
