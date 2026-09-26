// Single source of truth for the facts the legal pages (/privacy, /terms,
// /dpa, /subprocessors, /cookies, /security) and the cookie-consent banner
// share. Update a vendor or cookie HERE, not in the individual pages.
//
// Anything not yet verifiable from the code or company records is left as a
// visible "{{VERIFY: ...}}" marker on purpose, so an unreviewed fact can't
// quietly ship as if it were confirmed. See GDPR-COMPLIANCE-CLAUDE.md.

export const COMPANY = {
  legalName: "Mielikkix AS",
  orgNumber: "{{VERIFY: org. number}}",
  address: "{{VERIFY: registered address}}",
  country: "Norway",
  privacyEmail: "post@mielikkix.no",
} as const;

/**
 * Version string + "last updated" date per document. Bump the version when the text changes materially.
 * terms/dpa versions are also recorded on every sign-up (consent_records) -- keep them identical to
 * TERMS_VERSION / DPA_VERSION in apps/api/app/core/legal.py.
 */
export const LEGAL_DOCS = {
  privacy: { version: "privacy-2026-09-25", updated: "2026-09-25" },
  terms: { version: "terms-2026-09-25", updated: "2026-09-25" },
  dpa: { version: "dpa-2026-09-25", updated: "2026-09-25" },
  subprocessors: { version: "subprocessors-2026-09-25", updated: "2026-09-25" },
  cookies: { version: "cookies-2026-09-25", updated: "2026-09-25" },
  security: { version: "security-2026-09-25", updated: "2026-09-25" },
} as const;

/**
 * Cookie-consent version. Bump when the set of optional cookies/purposes changes:
 * every visitor whose stored consent carries an older version is asked again.
 */
export const CONSENT_VERSION = "2026-09-25";
export const CONSENT_COOKIE = "mx_consent";
/** 12 months, the maximum we keep a consent choice before re-asking. */
export const CONSENT_MAX_AGE_SECONDS = 365 * 24 * 60 * 60;

type Bilingual = { en: string; no: string };

export interface Subprocessor {
  name: string;
  purpose: Bilingual;
  data: Bilingual;
  location: string;
  transfer: string;
}

// Derived from apps/api/app/core/config.py + requirements.txt, files/LLM_MODELS.md
// and infra/deploy/README.md (2026-09-25). Transfer mechanisms are not recorded
// anywhere in the repo, hence the VERIFY markers.
export const SUBPROCESSORS: Subprocessor[] = [
  {
    name: "Hostinger",
    purpose: { en: "VPS hosting of the app, API and database; hosting of this website", no: "VPS-hosting av appen, API-et og databasen; hosting av dette nettstedet" },
    data: { en: "All service data (stored)", no: "Alle tjenestedata (lagret)" },
    location: "{{VERIFY: data centre region}}",
    transfer: "{{VERIFY}}",
  },
  {
    name: "Groq",
    purpose: { en: "AI replies for the Chat Widget (default provider)", no: "AI-svar for chat-widgeten (standardleverandør)" },
    data: { en: "Chat messages, business knowledge base excerpts", no: "Chatmeldinger, utdrag fra bedriftens kunnskapsbase" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
  {
    name: "OpenAI",
    purpose: { en: "AI for Voice Receptionist, SEO and Review & Reputation agents", no: "AI for Voice Receptionist, SEO- og Review & Reputation-agentene" },
    data: { en: "Call transcripts, review texts, website content", no: "Samtaletranskripsjoner, anmeldelsestekster, nettstedsinnhold" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
  {
    name: "Anthropic",
    purpose: { en: "AI for Booking Assistant and Support Triage agents", no: "AI for Booking Assistant- og Support Triage-agentene" },
    data: { en: "Booking requests, support messages", no: "Bookingforespørsler, supportmeldinger" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
  {
    name: "Google (Gemini API)",
    purpose: { en: "Optional alternative AI provider, only if a business selects it", no: "Valgfri alternativ AI-leverandør, kun hvis en bedrift velger den" },
    data: { en: "Chat messages", no: "Chatmeldinger" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
  {
    name: "Google (Calendar, Business Profile, Analytics Data, Search Console, PageSpeed APIs)",
    purpose: { en: "Integrations a business chooses to connect (bookings, reviews, SEO audit)", no: "Integrasjoner en bedrift velger å koble til (booking, anmeldelser, SEO-revisjon)" },
    data: { en: "Appointment details, reviews, website metrics", no: "Avtaledetaljer, anmeldelser, nettstedsmålinger" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
  {
    name: "Twilio",
    purpose: { en: "Phone calls and speech-to-text for Voice Receptionist", no: "Telefonsamtaler og tale-til-tekst for Voice Receptionist" },
    data: { en: "Caller phone number, call audio", no: "Innringers telefonnummer, samtalelyd" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
  {
    name: "Resend",
    purpose: { en: "Transactional email (lead/booking notifications, password resets)", no: "Transaksjonell e-post (lead-/bookingvarsler, tilbakestilling av passord)" },
    data: { en: "Email address, email content", no: "E-postadresse, e-postinnhold" },
    location: "USA",
    transfer: "{{VERIFY: DPF or SCCs}}",
  },
];

/** Third parties that only a business's own connected account uses (not engaged by us on everyone's behalf). */
export const CUSTOMER_CONNECTED_SERVICES = ["Mailchimp (Email Marketing agent)", "Google Calendar", "Google Business Profile", "Google Analytics / Search Console"];

export type CookieKind = "cookie" | "localStorage" | "sessionStorage";

export interface CookieEntry {
  name: string;
  kind: CookieKind;
  surface: "website" | "app" | "widget";
  purpose: Bilingual;
  duration: Bilingual;
  party: "first" | "third";
  consentRequired: boolean;
}

// Verified by grepping website/src, website/public, apps/dashboard/src and
// apps/api for cookie / localStorage / sessionStorage writes (2026-09-25).
export const COOKIES: CookieEntry[] = [
  {
    name: CONSENT_COOKIE,
    kind: "cookie",
    surface: "website",
    purpose: { en: "Remembers your cookie choice", no: "Husker ditt valg om informasjonskapsler" },
    duration: { en: "12 months", no: "12 måneder" },
    party: "first",
    consentRequired: false,
  },
  {
    name: "mielikkix:lang",
    kind: "localStorage",
    surface: "website",
    purpose: { en: "Remembers the language you picked", no: "Husker språket du valgte" },
    duration: { en: "Until you clear it", no: "Til du sletter den" },
    party: "first",
    consentRequired: false,
  },
  {
    name: "mielikkix_currency",
    kind: "localStorage",
    surface: "website",
    purpose: { en: "Remembers the currency shown on pricing pages", no: "Husker valutaen som vises på prissidene" },
    duration: { en: "Until you clear it", no: "Til du sletter den" },
    party: "first",
    consentRequired: false,
  },
  {
    name: "mielikkix_exchange_rate_<CURRENCY>",
    kind: "localStorage",
    surface: "website",
    purpose: { en: "Caches today's exchange rate so prices load quickly", no: "Mellomlagrer dagens valutakurs så prisene lastes raskt" },
    duration: { en: "Refreshed after 24 hours", no: "Oppdateres etter 24 timer" },
    party: "first",
    consentRequired: false,
  },
  {
    name: "_ga",
    kind: "cookie",
    surface: "website",
    purpose: { en: "Google Analytics: distinguishes visitors (only after you accept analytics)", no: "Google Analytics: skiller besøkende fra hverandre (kun etter at du godtar analyse)" },
    duration: { en: "2 years", no: "2 år" },
    party: "first",
    consentRequired: true,
  },
  {
    name: "_ga_<ID>",
    kind: "cookie",
    surface: "website",
    purpose: { en: "Google Analytics: keeps session state (only after you accept analytics)", no: "Google Analytics: holder øktstatus (kun etter at du godtar analyse)" },
    duration: { en: "2 years", no: "2 år" },
    party: "first",
    consentRequired: true,
  },
  {
    name: "mielikkix_session",
    kind: "sessionStorage",
    surface: "widget",
    purpose: { en: "Keeps your chat conversation together; only written once you open the chat", no: "Holder chatsamtalen samlet; skrives først når du åpner chatten" },
    duration: { en: "Until the browser tab closes", no: "Til nettleserfanen lukkes" },
    party: "first",
    consentRequired: false,
  },
  {
    name: "access_token",
    kind: "cookie",
    surface: "app",
    purpose: { en: "Keeps you signed in to app.mielikkix.ai (httpOnly)", no: "Holder deg innlogget på app.mielikkix.ai (httpOnly)" },
    duration: { en: "24 hours", no: "24 timer" },
    party: "first",
    consentRequired: false,
  },
  {
    name: "mielikkix_dashboard_currency",
    kind: "localStorage",
    surface: "app",
    purpose: { en: "Remembers the currency shown in the dashboard", no: "Husker valutaen som vises i dashbordet" },
    duration: { en: "Until you clear it", no: "Til du sletter den" },
    party: "first",
    consentRequired: false,
  },
];
