// GA4 bootstrap for mielikkix.ai. Kept external (not inline) because the
// site's CSP (public/.htaccess) has no 'unsafe-inline' for script-src -- same
// reasoning as the /demo/*.js files (see ARCHITECTURE.md). Only runs when
// Layout.astro renders this tag, which only happens when PUBLIC_GA_MEASUREMENT_ID
// is set (see Layout.astro).
(function () {
  var id = document.currentScript.getAttribute("data-ga-id");
  if (!id) return;

  window.dataLayer = window.dataLayer || [];
  function gtag() {
    window.dataLayer.push(arguments);
  }
  window.gtag = gtag;

  gtag("js", new Date());
  gtag("config", id);
})();
