// Cookie consent for mielikkix.ai (GDPR + Norwegian ekomloven § 2-7b).
//
// Google Analytics is the only optional (consent-requiring) tracker on the
// site. Rules this module enforces:
//  - Nothing is requested from googletagmanager.com / google-analytics.com
//    until the visitor has actively accepted analytics. The gtag loader is
//    injected by this module only after that, never server-rendered.
//  - Google Consent Mode v2 defaults are all "denied" and set BEFORE gtag
//    loads; only analytics_storage is ever upgraded to "granted" (ads never).
//  - "Reject all" is exactly as prominent as "Accept all"; withdrawing is as
//    easy as giving (footer "Cookie settings" link reopens the banner).
//  - The choice lives in a first-party cookie for at most 12 months and
//    carries CONSENT_VERSION, so bumping the version re-asks everyone.

import { CONSENT_COOKIE, CONSENT_MAX_AGE_SECONDS, CONSENT_VERSION } from "../config/legal";

export interface ConsentState {
  analytics: boolean;
}

type GtagFn = (...args: unknown[]) => void;
declare global {
  interface Window {
    dataLayer: unknown[];
    gtag?: GtagFn;
    [key: `ga-disable-${string}`]: boolean;
  }
}

export function readConsent(): ConsentState | null {
  const raw = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${CONSENT_COOKIE}=`))
    ?.slice(CONSENT_COOKIE.length + 1);
  if (!raw) return null;
  const fields = new URLSearchParams(decodeURIComponent(raw));
  // A choice given under an older consent version doesn't count -- ask again.
  if (fields.get("v") !== CONSENT_VERSION) return null;
  return { analytics: fields.get("analytics") === "1" };
}

export function writeConsent(state: ConsentState): void {
  const value = new URLSearchParams({
    v: CONSENT_VERSION,
    analytics: state.analytics ? "1" : "0",
    t: new Date().toISOString(),
  }).toString();
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${CONSENT_COOKIE}=${encodeURIComponent(value)}; Max-Age=${CONSENT_MAX_AGE_SECONDS}; Path=/; SameSite=Lax${secure}`;
}

function ensureGtagStub(): GtagFn {
  window.dataLayer = window.dataLayer || [];
  if (!window.gtag) {
    window.gtag = function gtag() {
      // gtag.js requires the Arguments object itself, not an array copy.
      // eslint-disable-next-line prefer-rest-params
      window.dataLayer.push(arguments);
    };
  }
  return window.gtag;
}

let gaLoaded = false;

/** Loads GA4 with analytics consent granted. Only ever call after an explicit opt-in. */
export function enableAnalytics(measurementId: string): void {
  if (!measurementId) return;
  window[`ga-disable-${measurementId}`] = false;
  const gtag = ensureGtagStub();

  if (!gaLoaded) {
    gtag("consent", "default", {
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
      analytics_storage: "denied",
    });
  }
  gtag("consent", "update", { analytics_storage: "granted" });

  if (gaLoaded) return;
  gaLoaded = true;
  gtag("js", new Date());
  gtag("config", measurementId, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  });
  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.appendChild(script);
}

/** Stops GA on this page (if it was running) and removes its cookies. */
export function disableAnalytics(measurementId: string): void {
  if (measurementId) window[`ga-disable-${measurementId}`] = true;
  window.gtag?.("consent", "update", { analytics_storage: "denied" });
  deleteGaCookies();
}

function deleteGaCookies(): void {
  const names = document.cookie
    .split("; ")
    .map((c) => c.split("=")[0])
    .filter((n) => n === "_ga" || n.startsWith("_ga_") || n === "_gid" || n === "_gat");
  // GA sets its cookies on the registrable domain (".mielikkix.ai"), so
  // expire each on every parent domain level as well as the bare host.
  const parts = location.hostname.split(".");
  const domains = [""];
  for (let i = 0; i < parts.length - 1; i++) domains.push(`; Domain=.${parts.slice(i).join(".")}`);
  for (const name of names) {
    for (const domain of domains) {
      document.cookie = `${name}=; Max-Age=0; Path=/${domain}`;
    }
  }
}
