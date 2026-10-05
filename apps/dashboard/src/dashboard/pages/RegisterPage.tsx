import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../../shared/store/authStore'
import { Input } from '../../shared/components/Input'
import { Button } from '../../shared/components/Button'
import { AuthLayout } from '../components/AuthLayout'
import { countryOptions, guessCountry } from '../../shared/countries'
import { marketingUrl, useAuthLang, type AuthLang } from '../../shared/authLang'

// QA 2026-10-05 (BUG-15): English only, even from the Norwegian site.
const INDUSTRIES = ['retail', 'restaurant', 'clinic', 'real_estate', 'service', 'other'] as const

const STRINGS = {
  en: {
    title: 'Create your account',
    intro: 'Start on the free plan: no card needed, and it never expires.',
    businessName: 'Business name',
    slug: 'Business slug (URL-friendly)',
    industry: 'Industry',
    selectIndustry: 'Select your industry',
    industries: { retail: 'Retail', restaurant: 'Restaurant', clinic: 'Clinic', real_estate: 'Real estate', service: 'Services', other: 'Other' },
    name: 'Your name',
    email: 'Email',
    password: 'Password',
    country: 'Country',
    selectCountry: 'Select your country',
    agreements: 'Agreements',
    termsBefore: 'I agree to the ',
    terms: 'Terms of Service',
    and: ' and ',
    dpa: 'Data Processing Agreement',
    age: 'I confirm I am 18 or older and signing up on behalf of a business.',
    marketing: 'Send me product updates and tips by email. You can unsubscribe anytime. (Optional)',
    errAgreements: 'Please accept the Terms of Service and Data Processing Agreement, and confirm you are 18 or older and signing up for a business.',
    errCountry: 'Please select your country.',
    errIndustry: 'Please select your industry.',
    errFailed: 'Registration failed.',
    submit: 'Create account',
    privacyBefore: 'We process your account data to provide the service. Read our ',
    privacy: 'Privacy Policy',
    haveAccount: 'Already have an account?',
    signIn: 'Sign in',
  },
  no: {
    title: 'Opprett konto',
    intro: 'Start på gratisplanen: ingen kort nødvendig, og den utløper aldri.',
    businessName: 'Bedriftsnavn',
    slug: 'Kortnavn for bedriften (brukes i URL-er)',
    industry: 'Bransje',
    selectIndustry: 'Velg bransje',
    industries: { retail: 'Butikk', restaurant: 'Restaurant', clinic: 'Klinikk', real_estate: 'Eiendom', service: 'Tjenester', other: 'Annet' },
    name: 'Navnet ditt',
    email: 'E-post',
    password: 'Passord',
    country: 'Land',
    selectCountry: 'Velg land',
    agreements: 'Avtaler',
    termsBefore: 'Jeg godtar ',
    terms: 'vilkårene for bruk',
    and: ' og ',
    dpa: 'databehandleravtalen',
    age: 'Jeg bekrefter at jeg er 18 år eller eldre og registrerer meg på vegne av en bedrift.',
    marketing: 'Send meg produktnyheter og tips på e-post. Du kan melde deg av når som helst. (Valgfritt)',
    errAgreements: 'Godta vilkårene for bruk og databehandleravtalen, og bekreft at du er 18 år eller eldre og registrerer deg for en bedrift.',
    errCountry: 'Velg land.',
    errIndustry: 'Velg bransje.',
    errFailed: 'Registreringen mislyktes.',
    submit: 'Opprett konto',
    privacyBefore: 'Vi behandler kontoopplysningene dine for å levere tjenesten. Les ',
    privacy: 'personvernerklæringen',
    haveAccount: 'Har du allerede en konto?',
    signIn: 'Logg inn',
  },
} satisfies Record<AuthLang, unknown>

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
  const lang = useAuthLang()
  const t = STRINGS[lang]
  const countries = useMemo(() => countryOptions(lang === 'no' ? 'nb' : 'en'), [lang])
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
      setError(t.errAgreements)
      return
    }
    if (!form.industry) {
      setError(t.errIndustry)
      return
    }
    if (!form.country) {
      setError(t.errCountry)
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
      setError(msg || t.errFailed)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout cardClassName="max-w-md">
      <h1 className="text-4xl font-bold text-slate-900 mb-1">{t.title}</h1>
      <p className="text-base text-slate-500 mb-6">{t.intro}</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label={t.businessName} value={form.business_name} onChange={set('business_name')} autoComplete="organization" required />
        <Input label={t.slug} value={form.business_slug} onChange={set('business_slug')} placeholder={lang === 'no' ? 'min-butikk' : 'my-shop'} required />
        <div>
          <label htmlFor="register-industry" className="block text-base font-medium text-slate-700 mb-1">{t.industry}</label>
          <select
            id="register-industry"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.industry}
            onChange={set('industry')}
            required
          >
            <option value="" disabled>{t.selectIndustry}</option>
            {INDUSTRIES.map((i) => (
              <option key={i} value={i}>{t.industries[i]}</option>
            ))}
          </select>
        </div>
        <Input label={t.name} value={form.full_name} onChange={set('full_name')} autoComplete="name" required />
        <Input label={t.email} type="email" value={form.email} onChange={set('email')} autoComplete="email" required />
        <Input label={t.password} type="password" value={form.password} onChange={set('password')} autoComplete="new-password" required />
        <div>
          <label htmlFor="register-country" className="block text-base font-medium text-slate-700 mb-1">{t.country}</label>
          <select
            id="register-country"
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-base"
            value={form.country}
            onChange={set('country')}
            required
          >
            <option value="" disabled>{t.selectCountry}</option>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
        </div>
        <fieldset className="space-y-3 pt-1">
          <legend className="sr-only">{t.agreements}</legend>
          <Checkbox id="register-terms" checked={termsAccepted} onChange={setTermsAccepted} required>
            {t.termsBefore}<ExternalLink href={marketingUrl('/terms/', lang)}>{t.terms}</ExternalLink>{t.and}
            <ExternalLink href={marketingUrl('/dpa/', lang)}>{t.dpa}</ExternalLink>.
          </Checkbox>
          <Checkbox id="register-age" checked={ageConfirmed} onChange={setAgeConfirmed} required>
            {t.age}
          </Checkbox>
          <Checkbox id="register-marketing" checked={marketingOptIn} onChange={setMarketingOptIn}>
            {t.marketing}
          </Checkbox>
        </fieldset>
        {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">{t.submit}</Button>
        <p className="text-sm text-slate-500">
          {t.privacyBefore}
          <ExternalLink href={marketingUrl('/privacy/', lang)}>{t.privacy}</ExternalLink>.
        </p>
      </form>
      <p className="mt-4 text-center text-base text-slate-500">
        {t.haveAccount}{' '}
        <Link to="/login" className="text-brand-600 font-medium hover:underline">{t.signIn}</Link>
      </p>
    </AuthLayout>
  )
}
