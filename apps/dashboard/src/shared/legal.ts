// The marketing site (website/) is a separate Astro app/deployment; astro.config.mjs
// there defines the same production domain. Update both together if it changes.
export const MARKETING_URL = 'https://mielikkix.ai'

// Legal pages live on the marketing site (bilingual EN/NO there) -- see
// website/src/config/legal.ts for their versions.
export const LEGAL_URLS = {
  privacy: `${MARKETING_URL}/privacy`,
  terms: `${MARKETING_URL}/terms`,
  dpa: `${MARKETING_URL}/dpa`,
  cookies: `${MARKETING_URL}/cookies`,
} as const
