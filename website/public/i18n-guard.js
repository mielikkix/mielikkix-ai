// Runs before paint, in <head>:
//  1. A /no/... URL is the Norwegian site (QA 2026-10-05, BUG-13): remember
//     that choice, so every later page, demo script and the chat widget follow it.
//  2. A returning Norwegian visitor who lands on an English URL that has a
//     Norwegian copy (<link rel="alternate" hreflang="nb">, placed above this
//     script by Layout.astro) goes to that copy, so the address bar always
//     shows the language on screen. Crawlers have no stored choice, so they
//     index both URLs as they are.
//  3. Otherwise, a non-default stored language hides <body> (html.i18n-loading,
//     see global.css) until the client-side i18n bootstrap applies it, avoiding
//     an English flash on pages that have no Norwegian copy.
//
// Kept as an external file (rather than an inline <script>) so it isn't blocked by the
// site's Content-Security-Policy, which has no 'unsafe-inline' for script-src.
try {
  var path = location.pathname;
  if (path === "/no" || path.indexOf("/no/") === 0) {
    localStorage.setItem("mielikkix:lang", "no");
  } else {
    var storedLang = localStorage.getItem("mielikkix:lang");
    var norwegianCopy = document.querySelector('link[rel="alternate"][hreflang="nb"]');
    if (storedLang === "no" && norwegianCopy) {
      location.replace(new URL(norwegianCopy.href).pathname + location.search + location.hash);
    } else if (storedLang && storedLang !== "en") {
      document.documentElement.classList.add("i18n-loading");
    }
  }
} catch (_e) {
  /* localStorage unavailable (privacy mode, etc.) — the URL alone decides the language */
}
