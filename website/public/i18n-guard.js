// Runs before paint: if a returning visitor has a non-default language stored, hide
// <body> (see html.i18n-loading in global.css) until the client-side i18n bootstrap
// (at the end of <body>) applies it, avoiding an English flash.
//
// Kept as an external file (rather than an inline <script>) so it isn't blocked by the
// site's Content-Security-Policy, which has no 'unsafe-inline' for script-src.
try {
  var storedLang = localStorage.getItem("mielikkix:lang");
  if (storedLang && storedLang !== "en") {
    document.documentElement.classList.add("i18n-loading");
  }
} catch (_e) {
  /* localStorage unavailable (privacy mode, etc.) — fall back to English, no guard needed */
}
