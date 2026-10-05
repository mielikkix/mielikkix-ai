// The API answers errors with an English `detail` string. The ones a business
// user can actually run into are mapped to translated messages here; anything
// else (rare, technical) is shown as the server sent it, which is still better
// than a generic "something went wrong". The server text stays English on
// purpose: it is also what logs and API clients see.

import { translate, type MessageKey, type Vars } from './core'
import { currentLocale } from './index'

type Rule = [RegExp, MessageKey, ((m: RegExpMatchArray) => Vars)?]

const RULES: Rule[] = [
  [/^Invalid credentials$/, 'errors.api.invalidCredentials'],
  [/^Email already registered$/, 'errors.api.emailTaken'],
  [/^Business slug already taken$/, 'errors.api.slugTaken'],
  [/^Invalid or expired reset link$/, 'errors.api.resetLinkInvalid'],
  [/Password must be at least 10 characters long/, 'errors.api.passwordTooShort'],
  [/Select a valid country/, 'errors.api.invalidCountry'],
  [/You must accept the Terms of Service/, 'errors.api.termsRequired'],
  [/You must confirm you are 18 or older/, 'errors.api.ageRequired'],
  [/This field can't be empty\./, 'errors.api.fieldRequired'],
  [/value is not a valid email address/, 'errors.api.invalidEmail'],
  [/Enter a full web address/, 'errors.api.fullUrlRequired'],
  [/^Enter a website address/, 'errors.api.websiteRequired'],
  [/^Not authenticated$/, 'errors.api.notAuthenticated'],
  [/^Only the account owner can do this\.$/, 'errors.api.ownerOnly'],
  [/^The business name you typed doesn't match\.$/, 'errors.api.businessNameMismatch'],
  [/^This is a platform operator account/, 'errors.api.platformAccount'],
  [/^File too large$/, 'errors.api.fileTooLarge'],
  [/^Page is too large$/, 'errors.api.pageTooLarge'],
  [/^File type \.(\w+) not supported$/, 'errors.api.fileType', (m) => ({ ext: m[1] })],
  [/^'(.+)' has already been uploaded/, 'errors.api.alreadyUploaded', (m) => ({ name: m[1] })],
  [/^Could not fetch that URL$|^URL returned status \d+$|^Could not resolve URL host$/, 'errors.api.fetchFailed'],
  [/^Invalid URL$|^Only http\/https URLs are supported$/, 'errors.api.invalidUrl'],
  [/^URLs pointing to private\/internal addresses/, 'errors.api.privateUrl'],
  [/^Couldn't find any pages to import from that site\.$/, 'errors.api.noPagesFound'],
  [/^Only web pages can be fetched again/, 'errors.api.refetchFileOnly'],
  [/^Your plan's document upload limit has been reached/, 'errors.api.documentLimit'],
  [/^Your plan only supports USD pricing/, 'errors.api.currencyPlan'],
  [/^Custom branding isn't available on your plan/, 'errors.api.brandingPlan'],
  [/^Your plan includes up to (\d+) days of conversation history/, 'errors.api.retentionPlan', (m) => ({ days: Number(m[1]) })],
  [/^(.+) is already registered( for SEO audits)?\.$/, 'errors.api.websiteExists', (m) => ({ site: m[1] })],
  [/^You've registered (\d+) websites, the limit/, 'errors.api.websiteLimit', (m) => ({ limit: Number(m[1]) })],
  [/^(.+) isn't active on your account\. Purchase it/, 'errors.api.agentInactive', (m) => ({ name: m[1] })],
  [/isn't available on the (.+) plan\. Upgrade to unlock it\.$/, 'errors.api.featurePlan', (m) => ({ plan: m[1] })],
  [/is coming soon and isn't available yet\.$/, 'errors.api.featureSoon'],
  [/isn't configured on this server yet\.$/, 'errors.api.notConfigured'],
  [/^No (Mailchimp|Google Business Profile) connection yet/, 'errors.api.notConnected', (m) => ({ service: m[1] })],
  [/^Couldn't reach Mailchimp/, 'errors.api.mailchimpDown'],
  [/^Please accept all updated documents/, 'errors.api.acceptDocuments'],
  [/ not found$/, 'errors.api.notFound'],
]

/** A translated message for a known server error text, or null. */
export function translateApiDetail(detail: string): string | null {
  const text = detail.replace(/^Value error, /, '').trim()
  for (const [pattern, key, vars] of RULES) {
    const m = text.match(pattern)
    if (m) return translate(currentLocale(), key, vars?.(m))
  }
  return null
}

/**
 * The message to show for a failed API call: the translated version of the
 * server's error when known, the server's own text otherwise, or `fallback`
 * (e.g. 'errors.generic') when there is no text at all.
 */
export function apiErrorMessage(err: unknown, fallback: MessageKey = 'errors.generic'): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return translateApiDetail(detail) ?? detail
  }
  return translate(currentLocale(), fallback)
}
