/**
 * The ONLY place prices live. Every pricing card, comparison table, chart,
 * bundle saving, yearly price and JSON-LD Offer on the site is computed from
 * this file -- change a number here and nothing else needs editing.
 *
 * All prices are fixed NOK per month, excluding 25% MVA (sold to businesses).
 * No live currency conversion. `soon: true` marks a feature or limit that is
 * sold on the tier but not built yet: it renders with a "Coming soon" label.
 * The app's own copy of the Chat Widget and SEO prices lives in
 * apps/api/app/core/plans.py and agent_catalog.py -- keep them in step.
 * Limit/overage rules are documented for the app in docs/pricing-rules.md.
 */

export type TierId = "free" | "start" | "business" | "growth";
export type ProductId =
  | "chat-widget"
  | "voice-receptionist"
  | "booking-assistant"
  | "support-triage"
  | "review-reputation"
  | "seo-audit"
  | "custom-agents";
export type Lang = "en" | "no";

export interface Text {
  en: string;
  no: string;
}

export interface Included {
  label: Text;
  value: number | Text;
  /** Sold on this tier but not built yet. */
  soon?: boolean;
}

export interface Feature extends Text {
  soon?: boolean;
}

export interface Tier {
  id: TierId;
  priceNokMonthly: number | null; // null = free
  priceFrom?: boolean; // true -> "from 14 900 kr"
  recommended?: boolean; // star badge (always the Business tier)
  managed?: boolean; // SEO Business/Growth -> "Managed" label
  /** Included units on the chart's usage axis; null = not a fixed number ("Custom"). */
  usage: number | null;
  included: Included[];
  overage?: { unit: Text; priceNok: number } | null;
  features: Feature[];
  minTermMonths?: number;
  stripePriceId?: string | null;
}

export interface Faq {
  q: Text;
  a: Text;
}

export interface Product {
  id: ProductId;
  name: Text;
  emoji: string;
  tagline: Text;
  usageUnit: Text; // chart axis, plural
  usageUnitOne: Text; // singular, for "price per ..."
  tiers: Tier[];
  faq: Faq[];
  /** Page with the live demo or product details. */
  detailHref: string;
}

// Custom agents: the owner is still deciding between this minimum term and
// month-to-month with a setup fee (15 000-75 000 kr). Change it here.
export const CUSTOM_AGENT_MIN_TERM_MONTHS = 12;
export const SHOW_VISIBILITY_BUNDLE = false;

export const PRICING_META = {
  currency: "NOK",
  vatRate: 0.25,
  pricesExcludeVat: true,
  yearlyMonthsCharged: 10, // "2 months free"
  audience: "business",
} as const;

export const TIER_NAMES: Record<TierId, Text> = {
  free: { en: "Free", no: "Gratis" },
  start: { en: "Start", no: "Start" },
  business: { en: "Business", no: "Business" },
  growth: { en: "Growth", no: "Growth" },
};

const t = (en: string, no: string): Text => ({ en, no });
const soon = (en: string, no: string): Feature => ({ en, no, soon: true });
const UNLIMITED = t("Unlimited", "Ubegrenset");

// ---------------------------------------------------------------------------
// Shared FAQ answers (Step 4 rules). One wording, reused by every product.
// ---------------------------------------------------------------------------

const FAQ_SOFT_LIMIT = (unit: Text): Faq => ({
  q: t("What happens if I reach my limit?", "Hva skjer hvis jeg når grensen?"),
  a: t(
    `We email you at 80% and 100% of your monthly ${unit.en}, so you can upgrade in time. There are no surprise overage charges: the assistant keeps working up to 10% over the limit, then shows a contact form instead so you don't lose the lead. The limit resets at the start of each month.`,
    `Vi sender deg en e-post ved 80 % og 100 % av månedens ${unit.no}, så du rekker å oppgradere. Det kommer ingen overraskende tilleggskostnader: assistenten fortsetter å svare opptil 10 % over grensen, og viser deretter et kontaktskjema slik at du ikke mister henvendelsen. Grensen nullstilles ved starten av hver måned.`,
  ),
});

const FAQ_CHANGE_PLAN: Faq = {
  q: t("Can I change or cancel my plan?", "Kan jeg bytte eller si opp planen?"),
  a: t(
    "Yes. Upgrades take effect immediately and the difference is prorated. Downgrades take effect from the next billing period. Monthly plans can be cancelled at any time, and you keep access until the end of the period you've paid for.",
    "Ja. Oppgraderinger gjelder med én gang, og mellomlegget beregnes forholdsmessig. Nedgraderinger gjelder fra neste faktureringsperiode. Månedlige planer kan sies opp når som helst, og du beholder tilgangen ut perioden du har betalt for.",
  ),
};

const FAQ_VAT: Faq = {
  q: t("Do the prices include VAT?", "Er MVA inkludert i prisene?"),
  a: t(
    "No. Prices are for businesses and exclude 25% Norwegian VAT (MVA), which is added to the invoice. Paying yearly costs 10 months' price for 12 months.",
    "Nei. Prisene gjelder bedrifter og er oppgitt eksklusive 25 % MVA, som legges til på fakturaen. Betaler du årlig, betaler du for 10 måneder og får 12.",
  ),
};

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

export const products: Product[] = [
  {
    id: "chat-widget",
    name: t("AI Chat Widget", "AI Chat Widget"),
    emoji: "💬",
    tagline: t(
      "An AI chatbot for your website, trained on your own FAQs, documents and catalog.",
      "En AI-chatbot for nettsiden din, trent på dine egne FAQ-er, dokumenter og produktkatalog.",
    ),
    usageUnit: t("conversations", "samtaler"),
    usageUnitOne: t("conversation", "samtale"),
    detailHref: "/features",
    tiers: [
      {
        id: "free",
        priceNokMonthly: null,
        usage: 50,
        included: [
          { label: t("AI conversations / month", "AI-samtaler / mnd"), value: 50 },
          { label: t("Websites", "Nettsider"), value: 1 },
          { label: t("Document uploads", "Dokumentopplastinger"), value: 2 },
          { label: t("Products in catalog", "Produkter i katalogen"), value: 10 },
          { label: t("Conversation history", "Samtalehistorikk"), value: t("7 days", "7 dager") },
          { label: t("Languages", "Språk"), value: 1 },
        ],
        features: [
          t("Knowledge base from your documents and website", "Kunnskapsbase fra dokumentene og nettsiden din"),
          t("Lead capture", "Leadfangst"),
          t("Email notifications", "E-postvarsler"),
          t("Basic analytics", "Grunnleggende analyse"),
        ],
      },
      {
        id: "start",
        priceNokMonthly: 490,
        usage: 1000,
        included: [
          { label: t("AI conversations / month", "AI-samtaler / mnd"), value: 1000 },
          { label: t("Websites", "Nettsider"), value: 1 },
          { label: t("Document uploads", "Dokumentopplastinger"), value: 20 },
          { label: t("Products in catalog", "Produkter i katalogen"), value: 100 },
          { label: t("Conversation history", "Samtalehistorikk"), value: t("90 days", "90 dager") },
          { label: t("Languages", "Språk"), value: 2 },
        ],
        features: [
          t("Knowledge base from your documents and website", "Kunnskapsbase fra dokumentene og nettsiden din"),
          t("Lead capture", "Leadfangst"),
          t("Email notifications", "E-postvarsler"),
          t("Custom branding", "Egen merkevare og farger"),
          t("Standard analytics", "Standard analyse"),
        ],
      },
      {
        id: "business",
        priceNokMonthly: 990,
        recommended: true,
        usage: 5000,
        included: [
          { label: t("AI conversations / month", "AI-samtaler / mnd"), value: 5000 },
          { label: t("Websites", "Nettsider"), value: 3 },
          { label: t("Document uploads", "Dokumentopplastinger"), value: UNLIMITED },
          { label: t("Products in catalog", "Produkter i katalogen"), value: UNLIMITED },
          { label: t("Conversation history", "Samtalehistorikk"), value: t("Up to 12 months", "Opptil 12 måneder") },
          { label: t("Languages", "Språk"), value: 10 },
        ],
        features: [
          t("Knowledge base from your documents and website", "Kunnskapsbase fra dokumentene og nettsiden din"),
          t("Lead capture", "Leadfangst"),
          t("Email notifications", "E-postvarsler"),
          t("Custom branding", "Egen merkevare og farger"),
          t("Advanced analytics", "Avansert analyse"),
          t("Priority support", "Prioritert support"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 1990,
        usage: 20000,
        included: [
          { label: t("AI conversations / month", "AI-samtaler / mnd"), value: 20000 },
          { label: t("Websites", "Nettsider"), value: 10 },
          { label: t("Document uploads", "Dokumentopplastinger"), value: UNLIMITED },
          { label: t("Products in catalog", "Produkter i katalogen"), value: UNLIMITED },
          { label: t("Conversation history", "Samtalehistorikk"), value: t("Up to 12 months", "Opptil 12 måneder") },
          { label: t("Languages", "Språk"), value: 10 },
        ],
        features: [
          t("Knowledge base from your documents and website", "Kunnskapsbase fra dokumentene og nettsiden din"),
          t("Lead capture", "Leadfangst"),
          t("Email notifications", "E-postvarsler"),
          t("Custom branding", "Egen merkevare og farger"),
          t("Advanced analytics", "Avansert analyse"),
          t("Priority support", "Prioritert support"),
          t("API access included", "API-tilgang inkludert"),
        ],
      },
    ],
    faq: [
      FAQ_SOFT_LIMIT(t("conversations", "samtaler")),
      {
        q: t("Is the Free plan really free?", "Er gratisplanen virkelig gratis?"),
        a: t(
          "Yes. It's a permanent plan, not a time-limited trial, with deliberate limits (1 website, 50 conversations a month) so you can try the product properly. No card needed.",
          "Ja. Det er en permanent plan, ikke en tidsbegrenset prøveperiode, med bevisste begrensninger (1 nettside, 50 samtaler i måneden) slik at du kan prøve produktet ordentlig. Du trenger ikke betalingskort.",
        ),
      },
      FAQ_CHANGE_PLAN,
      FAQ_VAT,
    ],
  },
  {
    id: "voice-receptionist",
    name: t("Voice Receptionist", "Voice Receptionist"),
    emoji: "📞",
    tagline: t(
      "An AI receptionist that answers your phone 24/7, in Norwegian and English.",
      "En AI-resepsjonist som svarer telefonen døgnet rundt, på norsk og engelsk.",
    ),
    usageUnit: t("minutes", "minutter"),
    usageUnitOne: t("minute", "minutt"),
    detailHref: "/demo/voice-receptionist",
    tiers: [
      {
        id: "start",
        priceNokMonthly: 590,
        usage: 100,
        included: [
          { label: t("Call minutes / month", "Samtaleminutter / mnd"), value: 100 },
          { label: t("Norwegian phone numbers", "Norske telefonnumre"), value: 1 },
        ],
        overage: { unit: t("minute", "minutt"), priceNok: 4 },
        features: [
          t("Answers calls 24/7", "Svarer anrop døgnet rundt"),
          t("Norwegian and English", "Norsk og engelsk"),
          t("Answers from your own business information", "Svarer ut fra bedriftens egen informasjon"),
          t("Books appointments after the caller confirms", "Booker timer etter at innringeren bekrefter"),
        ],
      },
      {
        id: "business",
        priceNokMonthly: 1790,
        recommended: true,
        usage: 500,
        included: [
          { label: t("Call minutes / month", "Samtaleminutter / mnd"), value: 500 },
          { label: t("Norwegian phone numbers", "Norske telefonnumre"), value: 1 },
        ],
        overage: { unit: t("minute", "minutt"), priceNok: 3.5 },
        features: [
          t("Answers calls 24/7", "Svarer anrop døgnet rundt"),
          t("Norwegian and English", "Norsk og engelsk"),
          t("Answers from your own business information", "Svarer ut fra bedriftens egen informasjon"),
          t("Books appointments after the caller confirms", "Booker timer etter at innringeren bekrefter"),
          soon("Call summaries", "Samtalesammendrag"),
          soon("Transfer to staff", "Viderekobling til ansatte"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 3990,
        usage: 1500,
        included: [
          { label: t("Call minutes / month", "Samtaleminutter / mnd"), value: 1500 },
          { label: t("Norwegian phone numbers", "Norske telefonnumre"), value: t("3 (one per location)", "3 (ett per lokasjon)"), soon: true },
        ],
        overage: { unit: t("minute", "minutt"), priceNok: 3 },
        features: [
          t("Answers calls 24/7", "Svarer anrop døgnet rundt"),
          t("Norwegian and English", "Norsk og engelsk"),
          t("Answers from your own business information", "Svarer ut fra bedriftens egen informasjon"),
          t("Books appointments after the caller confirms", "Booker timer etter at innringeren bekrefter"),
          soon("Call summaries", "Samtalesammendrag"),
          soon("Transfer to staff", "Viderekobling til ansatte"),
        ],
      },
    ],
    faq: [
      {
        q: t("What happens if I use more minutes than included?", "Hva skjer hvis jeg bruker flere minutter enn inkludert?"),
        a: t(
          "Calls are always answered. Extra minutes are billed monthly at the overage rate shown on your plan (4.00, 3.50 or 3.00 kr per minute excl. VAT), and you'll see them itemised on your invoice.",
          "Anrop blir alltid besvart. Ekstra minutter faktureres månedlig til tilleggsprisen på planen din (4,00, 3,50 eller 3,00 kr per minutt eks. mva.), og de spesifiseres på fakturaen.",
        ),
      },
      {
        q: t("Does the caller know it's an AI?", "Vet innringeren at det er en AI?"),
        a: t(
          "Yes. The greeting always says the caller is speaking with an AI assistant and that the call is transcribed, as the EU AI Act requires.",
          "Ja. Velkomsthilsenen sier alltid at innringeren snakker med en AI-assistent og at samtalen transkriberes, slik EUs KI-forordning krever.",
        ),
      },
      FAQ_CHANGE_PLAN,
      FAQ_VAT,
    ],
  },
  {
    id: "booking-assistant",
    name: t("Booking Assistant", "Booking Assistant"),
    emoji: "📅",
    tagline: t(
      "Customers book appointments in the chat, straight into your calendar.",
      "Kundene booker time i chatten, rett inn i kalenderen din.",
    ),
    usageUnit: t("calendars", "kalendere"),
    usageUnitOne: t("calendar", "kalender"),
    detailHref: "/demo/booking-assistant",
    tiers: [
      {
        id: "start",
        priceNokMonthly: 390,
        usage: 1,
        included: [
          { label: t("Staff calendars", "Ansattkalendere"), value: 1 },
          { label: t("Locations", "Lokasjoner"), value: 1 },
        ],
        features: [
          t("Booking in the chat widget", "Booking i chat-widgeten"),
          t("Live availability from Google Calendar", "Ledige tider i sanntid fra Google Kalender"),
          t("Email confirmations and reminders", "Bekreftelser og påminnelser på e-post"),
        ],
      },
      {
        id: "business",
        priceNokMonthly: 890,
        recommended: true,
        usage: 5,
        included: [
          { label: t("Staff calendars", "Ansattkalendere"), value: t("Up to 5", "Opptil 5"), soon: true },
          { label: t("Locations", "Lokasjoner"), value: 1 },
        ],
        features: [
          t("Booking in the chat widget", "Booking i chat-widgeten"),
          t("Live availability from Google Calendar", "Ledige tider i sanntid fra Google Kalender"),
          t("Email confirmations and reminders", "Bekreftelser og påminnelser på e-post"),
          soon("SMS reminders", "SMS-påminnelser"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 1790,
        usage: 15,
        included: [
          { label: t("Staff calendars", "Ansattkalendere"), value: t("Up to 15", "Opptil 15"), soon: true },
          { label: t("Locations", "Lokasjoner"), value: 3, soon: true },
        ],
        features: [
          t("Booking in the chat widget", "Booking i chat-widgeten"),
          t("Live availability from Google Calendar", "Ledige tider i sanntid fra Google Kalender"),
          t("Email confirmations and reminders", "Bekreftelser og påminnelser på e-post"),
          soon("SMS reminders", "SMS-påminnelser"),
        ],
      },
    ],
    faq: [
      {
        q: t("Is there a limit on bookings?", "Er det en grense for antall bookinger?"),
        a: t(
          "No. Plans differ by the number of staff calendars and locations, not by bookings, so there are no overage charges. Need more calendars? Upgrade at any time.",
          "Nei. Planene skiller seg på antall ansattkalendere og lokasjoner, ikke antall bookinger, så det kommer ingen tilleggskostnader. Trenger du flere kalendere? Oppgrader når som helst.",
        ),
      },
      {
        q: t("Which calendars work?", "Hvilke kalendere støttes?"),
        a: t(
          "Google Calendar today. The assistant reads live availability and only books a time after the customer confirms it.",
          "Google Kalender i dag. Assistenten leser ledige tider i sanntid og booker først når kunden har bekreftet tidspunktet.",
        ),
      },
      FAQ_CHANGE_PLAN,
      FAQ_VAT,
    ],
  },
  {
    id: "support-triage",
    name: t("Support Triage", "Support Triage"),
    emoji: "🎫",
    tagline: t(
      "Classifies and routes every support request the moment it arrives, and answers the easy ones.",
      "Klassifiserer og ruter hver supporthenvendelse idet den kommer inn, og svarer på de enkle.",
    ),
    usageUnit: t("tickets", "saker"),
    usageUnitOne: t("ticket", "sak"),
    detailHref: "/demo/support-triage",
    tiers: [
      {
        id: "start",
        priceNokMonthly: 990,
        usage: 500,
        included: [
          { label: t("Tickets / month", "Saker / mnd"), value: 500 },
          { label: t("Team seats", "Brukerplasser"), value: 3, soon: true },
        ],
        features: [
          t("Automatic classification and priority", "Automatisk klassifisering og prioritet"),
          t("Routing to the right team", "Ruting til riktig team"),
          t("Hands off to a person when unsure", "Sender videre til et menneske ved usikkerhet"),
        ],
      },
      {
        id: "business",
        priceNokMonthly: 2490,
        recommended: true,
        usage: 2000,
        included: [
          { label: t("Tickets / month", "Saker / mnd"), value: 2000 },
          { label: t("Team seats", "Brukerplasser"), value: 10, soon: true },
        ],
        features: [
          t("Automatic classification and priority", "Automatisk klassifisering og prioritet"),
          t("Routing to the right team", "Ruting til riktig team"),
          t("Hands off to a person when unsure", "Sender videre til et menneske ved usikkerhet"),
          t("AI-drafted replies", "AI-utkast til svar"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 4990,
        usage: 6000,
        included: [
          { label: t("Tickets / month", "Saker / mnd"), value: 6000 },
          { label: t("Team seats", "Brukerplasser"), value: UNLIMITED, soon: true },
        ],
        features: [
          t("Automatic classification and priority", "Automatisk klassifisering og prioritet"),
          t("Routing to the right team", "Ruting til riktig team"),
          t("Hands off to a person when unsure", "Sender videre til et menneske ved usikkerhet"),
          t("AI-drafted replies", "AI-utkast til svar"),
          soon("SLA rules", "SLA-regler"),
        ],
      },
    ],
    faq: [
      {
        q: t("What happens if I get more tickets than included?", "Hva skjer hvis jeg får flere saker enn inkludert?"),
        a: t(
          "Every ticket is still handled and there are no surprise overage charges. If you regularly go over your plan, we'll get in touch to suggest the right one.",
          "Alle saker blir fortsatt behandlet, og det kommer ingen overraskende tilleggskostnader. Går du jevnlig over planen din, tar vi kontakt og foreslår riktig plan.",
        ),
      },
      FAQ_CHANGE_PLAN,
      FAQ_VAT,
    ],
  },
  {
    id: "review-reputation",
    name: t("Review & Reputation", "Review & Reputation"),
    emoji: "⭐",
    tagline: t(
      "Analyses your reviews and drafts on-brand replies you approve before they're published.",
      "Analyserer anmeldelsene dine og skriver utkast til svar som du godkjenner før de publiseres.",
    ),
    usageUnit: t("locations", "lokasjoner"),
    usageUnitOne: t("location", "lokasjon"),
    detailHref: "/demo/review-reputation",
    tiers: [
      {
        id: "start",
        priceNokMonthly: 390,
        usage: 1,
        included: [{ label: t("Locations", "Lokasjoner"), value: 1 }],
        features: [
          t("Google reviews", "Google-anmeldelser"),
          t("AI reply drafts, published only after your approval", "AI-utkast til svar, publiseres først etter din godkjenning"),
          t("Sentiment and priority for every review", "Stemning og prioritet for hver anmeldelse"),
        ],
      },
      {
        id: "business",
        priceNokMonthly: 890,
        recommended: true,
        usage: 3,
        included: [{ label: t("Locations", "Lokasjoner"), value: 3, soon: true }],
        features: [
          t("Google reviews", "Google-anmeldelser"),
          t("AI reply drafts, published only after your approval", "AI-utkast til svar, publiseres først etter din godkjenning"),
          t("Sentiment and priority for every review", "Stemning og prioritet for hver anmeldelse"),
          soon("Facebook and Trustpilot reviews", "Anmeldelser fra Facebook og Trustpilot"),
          soon("Review requests to customers", "Forespørsler om anmeldelser til kunder"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 1990,
        usage: 10,
        included: [{ label: t("Locations", "Lokasjoner"), value: 10, soon: true }],
        features: [
          t("Google reviews", "Google-anmeldelser"),
          t("AI reply drafts, published only after your approval", "AI-utkast til svar, publiseres først etter din godkjenning"),
          t("Sentiment and priority for every review", "Stemning og prioritet for hver anmeldelse"),
          soon("Facebook and Trustpilot reviews", "Anmeldelser fra Facebook og Trustpilot"),
          soon("Review requests to customers", "Forespørsler om anmeldelser til kunder"),
          t("Sentiment trend reports", "Rapporter om stemningsutvikling"),
        ],
      },
    ],
    faq: [
      {
        q: t("Is there a limit on reviews?", "Er det en grense for antall anmeldelser?"),
        a: t(
          "No. Plans differ by the number of business locations, not by reviews, so there are no overage charges.",
          "Nei. Planene skiller seg på antall lokasjoner, ikke antall anmeldelser, så det kommer ingen tilleggskostnader.",
        ),
      },
      {
        q: t("Are replies posted automatically?", "Publiseres svarene automatisk?"),
        a: t(
          "Never. Every AI draft waits for your approval, and you can edit it first.",
          "Aldri. Hvert AI-utkast venter på din godkjenning, og du kan redigere det først.",
        ),
      },
      FAQ_CHANGE_PLAN,
      FAQ_VAT,
    ],
  },
  {
    id: "seo-audit",
    name: t("SEO Audit & Optimize", "SEO Audit & Optimize"),
    emoji: "🔎",
    tagline: t(
      "A real crawl of your website, turned into a prioritised action plan. Do it yourself, or let us do it for you.",
      "En reell gjennomgang av nettsiden din, omgjort til en prioritert handlingsplan. Gjør det selv, eller la oss gjøre det for deg.",
    ),
    usageUnit: t("websites", "nettsider"),
    usageUnitOne: t("website", "nettside"),
    detailHref: "/agent-pricing#seo-audit",
    tiers: [
      {
        id: "free",
        priceNokMonthly: null,
        usage: 1,
        included: [
          { label: t("Websites", "Nettsider"), value: 1 },
          { label: t("Pages crawled", "Sider gjennomgått"), value: t("Up to 500", "Opptil 500") },
        ],
        features: [
          t("Technical, on-page and internal-linking audit", "Revisjon av teknisk SEO, innhold og intern lenking"),
          t("Prioritised action plan with AI summary", "Prioritert handlingsplan med AI-sammendrag"),
          t("Keyword ideas", "Forslag til nøkkelord"),
          t("PDF report and audit history", "PDF-rapport og revisjonshistorikk"),
          t("Unlimited re-audits", "Ubegrensede nye revisjoner"),
        ],
      },
      {
        id: "start",
        priceNokMonthly: 490,
        usage: 1,
        included: [
          { label: t("Websites", "Nettsider"), value: 1 },
          { label: t("Pages crawled", "Sider gjennomgått"), value: t("Up to 500", "Opptil 500") },
        ],
        features: [
          t("Everything in Free", "Alt i Gratis"),
          t("Google Analytics integration", "Integrasjon med Google Analytics"),
          t("Search Console integration", "Integrasjon med Search Console"),
          t("Scheduled audits", "Planlagte revisjoner"),
        ],
      },
      {
        id: "business",
        priceNokMonthly: 5900,
        recommended: true,
        managed: true,
        usage: 1,
        included: [
          { label: t("Websites", "Nettsider"), value: 1 },
          { label: t("Pages crawled", "Sider gjennomgått"), value: t("Up to 500", "Opptil 500") },
        ],
        features: [
          t("Everything in Start", "Alt i Start"),
          t("Monthly done-for-you fixes", "Månedlige forbedringer utført for deg"),
          t("Local business SEO", "Lokal SEO for bedriften"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 9900,
        managed: true,
        usage: 1,
        included: [
          { label: t("Websites", "Nettsider"), value: 1 },
          { label: t("Pages crawled", "Sider gjennomgått"), value: t("Larger sites, scoped with you", "Større nettsider, avtales med deg") },
        ],
        features: [
          t("Everything in Business", "Alt i Business"),
          t("Content plan", "Innholdsplan"),
          t("Monthly report", "Månedlig rapport"),
        ],
      },
    ],
    faq: [
      {
        q: t("What's the difference between self-serve and Managed?", "Hva er forskjellen på selvbetjent og Managed?"),
        a: t(
          "Free and Start give you the audit and action plan to work through yourself. On Business and Growth (Managed), our team makes the fixes for you every month.",
          "Gratis og Start gir deg revisjonen og handlingsplanen, som du følger opp selv. På Business og Growth (Managed) gjør teamet vårt forbedringene for deg hver måned.",
        ),
      },
      {
        q: t("Is anything published without my approval?", "Publiseres noe uten min godkjenning?"),
        a: t(
          "No. Nothing is changed on your website without your review and approval.",
          "Nei. Ingenting endres på nettsiden din uten at du har sett gjennom og godkjent det.",
        ),
      },
      FAQ_CHANGE_PLAN,
      FAQ_VAT,
    ],
  },
  {
    id: "custom-agents",
    name: t("Custom AI Agents", "Skreddersydde AI-agenter"),
    emoji: "🧠",
    tagline: t(
      "An AI agent built around your own workflow, tools and integrations.",
      "En AI-agent bygget rundt din egen arbeidsflyt, dine verktøy og integrasjoner.",
    ),
    usageUnit: t("integrations", "integrasjoner"),
    usageUnitOne: t("integration", "integrasjon"),
    detailHref: "/agents#custom",
    tiers: [
      {
        id: "start",
        priceNokMonthly: 2990,
        usage: 1,
        minTermMonths: CUSTOM_AGENT_MIN_TERM_MONTHS,
        included: [
          { label: t("Agents", "Agenter"), value: 1 },
          { label: t("Integrations", "Integrasjoner"), value: 1 },
          { label: t("Setup fee", "Etableringsgebyr"), value: t("None", "Ingen") },
        ],
        features: [t("One agent for one workflow", "Én agent for én arbeidsflyt"), t("Hosting and monitoring", "Drift og overvåking")],
      },
      {
        id: "business",
        priceNokMonthly: 6990,
        recommended: true,
        usage: 3,
        minTermMonths: CUSTOM_AGENT_MIN_TERM_MONTHS,
        included: [
          { label: t("Agents", "Agenter"), value: 1 },
          { label: t("Integrations", "Integrasjoner"), value: t("Up to 3", "Opptil 3") },
          { label: t("Setup fee", "Etableringsgebyr"), value: t("None", "Ingen") },
        ],
        features: [
          t("Multi-step agent", "Agent med flere steg"),
          t("Hosting and monitoring", "Drift og overvåking"),
        ],
      },
      {
        id: "growth",
        priceNokMonthly: 14900,
        priceFrom: true,
        usage: null,
        minTermMonths: CUSTOM_AGENT_MIN_TERM_MONTHS,
        included: [
          { label: t("Agents", "Agenter"), value: t("Multi-agent system", "System med flere agenter") },
          { label: t("Integrations", "Integrasjoner"), value: t("Scoped with you", "Avtales med deg") },
          { label: t("Setup fee", "Etableringsgebyr"), value: t("None", "Ingen") },
        ],
        features: [
          t("Multi-step agent", "Agent med flere steg"),
          t("Hosting and monitoring", "Drift og overvåking"),
          t("Service level agreement (SLA)", "Tjenestenivåavtale (SLA)"),
          t("Dedicated support", "Dedikert support"),
        ],
      },
    ],
    faq: [
      {
        q: t("Is there a minimum term?", "Er det en bindingstid?"),
        a: t(
          `Yes. Custom agents have a ${CUSTOM_AGENT_MIN_TERM_MONTHS}-month minimum term, and in return there is no setup fee. After that, the plan runs month to month.`,
          `Ja. Skreddersydde agenter har ${CUSTOM_AGENT_MIN_TERM_MONTHS} måneders bindingstid, og til gjengjeld er det ikke noe etableringsgebyr. Etter det løper avtalen månedlig.`,
        ),
      },
      {
        q: t("What does \"from 14 900 kr\" mean on Growth?", "Hva betyr «fra 14 900 kr» på Growth?"),
        a: t(
          "Multi-agent systems vary a lot, so we agree the exact monthly price with you after scoping. It never goes below the listed starting price.",
          "Systemer med flere agenter varierer mye, så vi avtaler den nøyaktige månedsprisen med deg etter en kartlegging. Den blir aldri lavere enn startprisen som står oppført.",
        ),
      },
      FAQ_VAT,
    ],
  },
];

// ---------------------------------------------------------------------------
// Add-ons and bundles
// ---------------------------------------------------------------------------

export interface Addon {
  id: string;
  name: Text;
  description: Text;
  priceNokMonthly: number;
  /** Not live yet: shown as "Coming soon" with no price. */
  comingSoon: boolean;
}

export const addons: Addon[] = [
  {
    id: "whatsapp-concierge",
    name: t("WhatsApp Concierge", "WhatsApp Concierge"),
    description: t(
      "Your chat assistant inside WhatsApp. Available on any Chat Widget plan.",
      "Chat-assistenten din inne i WhatsApp. Tilgjengelig på alle planer for Chat Widget.",
    ),
    priceNokMonthly: 490,
    // WhatsApp Business number is still pending Meta's approval (see /demo/whatsapp-concierge).
    comingSoon: true,
  },
];

export interface BundlePart {
  productId: ProductId;
  tierId: TierId;
}

export interface Bundle {
  id: string;
  name: Text;
  description: Text;
  priceNokMonthly: number;
  parts: BundlePart[];
  visible: boolean;
}

export const bundles: Bundle[] = [
  {
    id: "front-desk",
    name: t("Front Desk", "Front Desk"),
    description: t(
      "Chat, phone and bookings covered: everything a customer-facing front desk does.",
      "Chat, telefon og booking dekket: alt en resepsjon gjør for kundene.",
    ),
    priceNokMonthly: 2990,
    parts: [
      { productId: "chat-widget", tierId: "business" },
      { productId: "voice-receptionist", tierId: "business" },
      { productId: "booking-assistant", tierId: "business" },
    ],
    visible: true,
  },
  {
    id: "visibility",
    name: t("Visibility", "Synlighet"),
    description: t("Get found, get reviewed, and answer every visitor.", "Bli funnet, få anmeldelser, og svar hver besøkende."),
    priceNokMonthly: 1590,
    parts: [
      { productId: "seo-audit", tierId: "start" },
      { productId: "review-reputation", tierId: "business" },
      { productId: "chat-widget", tierId: "start" },
    ],
    visible: SHOW_VISIBILITY_BUNDLE,
  },
];

// ---------------------------------------------------------------------------
// Derived values and formatting -- the only helpers pages should use.
// ---------------------------------------------------------------------------

export function getProduct(id: ProductId): Product {
  const product = products.find((p) => p.id === id);
  if (!product) throw new Error(`[pricing] Unknown product "${id}"`);
  return product;
}

export function getTier(productId: ProductId, tierId: TierId): Tier {
  const tier = getProduct(productId).tiers.find((x) => x.id === tierId);
  if (!tier) throw new Error(`[pricing] ${productId} has no "${tierId}" tier`);
  return tier;
}

export function bundleListPrice(bundle: Bundle): number {
  return bundle.parts.reduce((sum, part) => sum + (getTier(part.productId, part.tierId).priceNokMonthly ?? 0), 0);
}

export function bundleSaving(bundle: Bundle): number {
  return bundleListPrice(bundle) - bundle.priceNokMonthly;
}

export function yearlyPrice(monthly: number): number {
  return monthly * PRICING_META.yearlyMonthsCharged;
}

export function withVat(amount: number): number {
  return Math.round(amount * (1 + PRICING_META.vatRate) * 100) / 100;
}

export function lowestPaidTier(product: Product): Tier {
  const paid = product.tiers.filter((x) => x.priceNokMonthly !== null);
  return paid.reduce((min, x) => ((x.priceNokMonthly as number) < (min.priceNokMonthly as number) ? x : min));
}

/** Effective price per included unit, or null when it can't be computed. */
export function pricePerUnit(tier: Tier): number | null {
  if (tier.priceNokMonthly === null || tier.usage === null || tier.usage === 0) return null;
  return tier.priceNokMonthly / tier.usage;
}

const NBSP = " ";

/** 1990 -> "1 990" (no, non-breaking space) / "1,990" (en). Up to 2 decimals. */
export function formatNumber(n: number, lang: Lang): string {
  const decimals = Number.isInteger(n) ? 0 : 2;
  const s = n.toLocaleString(lang === "no" ? "nb-NO" : "en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  // nb-NO uses a narrow NBSP (U+202F) or space depending on the ICU build; normalise to NBSP.
  return lang === "no" ? s.replace(/[\s ]/g, NBSP) : s;
}

/** "1 990 kr" / "NOK 1,990". */
export function formatNok(n: number, lang: Lang): string {
  return lang === "no" ? `${formatNumber(n, lang)}${NBSP}kr` : `NOK${NBSP}${formatNumber(n, lang)}`;
}

/** "1 990 kr/mnd eks. mva." / "NOK 1,990/month excl. VAT" (with "fra"/"from" when priceFrom). */
export function formatMonthly(tier: Pick<Tier, "priceNokMonthly" | "priceFrom">, lang: Lang): string {
  if (tier.priceNokMonthly === null) return lang === "no" ? "Gratis" : "Free";
  const from = tier.priceFrom ? (lang === "no" ? "fra " : "from ") : "";
  const suffix = lang === "no" ? "/mnd eks. mva." : "/month excl. VAT";
  return `${from}${formatNok(tier.priceNokMonthly, lang)}${suffix}`;
}

/** Price split for display: big amount + small period/VAT suffix. */
export function priceParts(
  tier: Pick<Tier, "priceNokMonthly" | "priceFrom">,
  lang: Lang,
  period: "month" | "year",
): { prefix: string; amount: string; suffix: string } {
  if (tier.priceNokMonthly === null) return { prefix: "", amount: lang === "no" ? "Gratis" : "Free", suffix: "" };
  const value = period === "year" ? yearlyPrice(tier.priceNokMonthly) : tier.priceNokMonthly;
  const prefix = tier.priceFrom ? (lang === "no" ? "fra " : "from ") : "";
  const unit = lang === "no" ? (period === "year" ? "/år" : "/mnd") : period === "year" ? "/year" : "/month";
  return { prefix, amount: formatNok(value, lang), suffix: `${unit} ${lang === "no" ? "eks. mva." : "excl. VAT"}` };
}

export function formatYearly(tier: Pick<Tier, "priceNokMonthly" | "priceFrom">, lang: Lang): string {
  if (tier.priceNokMonthly === null) return lang === "no" ? "Gratis" : "Free";
  const from = tier.priceFrom ? (lang === "no" ? "fra " : "from ") : "";
  const suffix = lang === "no" ? "/år eks. mva." : "/year excl. VAT";
  return `${from}${formatNok(yearlyPrice(tier.priceNokMonthly), lang)}${suffix}`;
}

export function formatValue(value: number | Text, lang: Lang): string {
  return typeof value === "number" ? formatNumber(value, lang) : value[lang];
}
