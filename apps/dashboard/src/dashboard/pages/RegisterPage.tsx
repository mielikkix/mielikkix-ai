import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../shared/store/authStore'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'
import { countryOptions, guessCountry } from '../../shared/countries'
import { marketingPath, useT } from '../../shared/i18n'
import { INTL_LOCALE } from '../../shared/i18n/core'
import { apiErrorMessage } from '../../shared/i18n/apiError'

// Stored values (sent to the API as-is); only the labels are translated.
const INDUSTRIES = ['retail', 'restaurant', 'clinic', 'real_estate', 'service', 'other'] as const

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
  const { t, locale } = useT()
  const register = useAuthStore((s) => s.register)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // Country names in the page's language (Intl.DisplayNames).
  const countries = useMemo(() => countryOptions(INTL_LOCALE[locale]), [locale])
  // No preselected industry (QA 2026-10-05, BUG-15: "retail" was preselected).
  const [form, setForm] = useState({
    business_name: '', business_slug: '', industry: '',
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
      setError(t('auth.register.errAgreements'))
      return
    }
    if (!form.industry) {
      setError(t('auth.register.errIndustry'))
      return
    }
    if (!form.country) {
      setError(t('auth.register.errCountry'))
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
      setError(apiErrorMessage(err, 'auth.register.errFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout cardClassName="max-w-md">
      <h1 className="text-4xl font-bold text-slate-900 mb-1">{t('auth.register.title')}</h1>
      <p className="text-base text-slate-500 mb-6">{t('auth.register.intro')}</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label={t('auth.register.businessName')} value={form.business_name} onChange={set('business_name')} autoComplete="organization" required />
        <Input
          label={t('auth.register.slug')}
          value={form.business_slug}
          onChange={set('business_slug')}
          placeholder={t('auth.register.slugPlaceholder')}
          required
        />
        <div>
          <label htmlFor="register-industry" className="block text-base font-medium text-slate-700 mb-1">{t('auth.register.industry')}</label>
          <select
            id="register-industry"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.industry}
            onChange={set('industry')}
            required
          >
            <option value="" disabled>{t('auth.register.selectIndustry')}</option>
            {INDUSTRIES.map((i) => (
              <option key={i} value={i}>{t(`auth.register.industries.${i}`)}</option>
            ))}
          </select>
        </div>
        <Input label={t('auth.register.fullName')} value={form.full_name} onChange={set('full_name')} autoComplete="name" required />
        <Input label={t('auth.register.email')} type="email" value={form.email} onChange={set('email')} autoComplete="email" required />
        <div>
          <Input
            label={t('auth.register.password')}
            type="password"
            value={form.password}
            onChange={set('password')}
            autoComplete="new-password"
            minLength={10}
            required
          />
          <p className="mt-1 text-sm text-slate-500">{t('auth.register.passwordHint')}</p>
        </div>
        <div>
          <label htmlFor="register-country" className="block text-base font-medium text-slate-700 mb-1">{t('auth.register.country')}</label>
          <select
            id="register-country"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.country}
            onChange={set('country')}
            required
          >
            <option value="" disabled>{t('auth.register.selectCountry')}</option>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
        </div>
        <fieldset className="space-y-3 pt-1">
          <legend className="sr-only">{t('auth.register.agreements')}</legend>
          <Checkbox id="register-terms" checked={termsAccepted} onChange={setTermsAccepted} required>
            {t('auth.register.termsBefore')}
            <ExternalLink href={marketingPath(locale, '/terms/')}>{t('auth.register.terms')}</ExternalLink>
            {t('auth.register.and')}
            <ExternalLink href={marketingPath(locale, '/dpa/')}>{t('auth.register.dpa')}</ExternalLink>
            {t('auth.register.termsAfter')}
          </Checkbox>
          <Checkbox id="register-age" checked={ageConfirmed} onChange={setAgeConfirmed} required>
            {t('auth.register.age')}
          </Checkbox>
          <Checkbox id="register-marketing" checked={marketingOptIn} onChange={setMarketingOptIn}>
            {t('auth.register.marketing')}
          </Checkbox>
        </fieldset>
        {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">{t('auth.register.submit')}</Button>
        <p className="text-sm text-slate-500">
          {t('auth.register.privacyBefore')}
          <ExternalLink href={marketingPath(locale, '/privacy/')}>{t('auth.register.privacy')}</ExternalLink>
          {t('auth.register.privacyAfter')}
        </p>
      </form>
      <p className="mt-4 text-center text-base text-slate-500">
        {t('auth.register.haveAccount')}{' '}
        <Link to="/login" className="text-brand-600 font-medium hover:underline">{t('auth.register.signIn')}</Link>
      </p>
    </AuthLayout>
  )
}
