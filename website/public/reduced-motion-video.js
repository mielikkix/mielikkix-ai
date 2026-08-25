// Pauses/un-autoplays a demo video for prefers-reduced-motion visitors.
// Kept as an external file (rather than an inline/bundled <script> in the
// .astro page) so it isn't blocked by the site's Content-Security-Policy,
// which has no 'unsafe-inline' for script-src -- see i18n-guard.js for the
// same pattern. Shared by index.astro and features.astro's own demo
// videos; the target element's id comes from this script tag's own
// data-video-id attribute.
const { videoId } = document.currentScript.dataset;
const video = document.getElementById(videoId);
if (video && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  video.removeAttribute("autoplay");
  video.removeAttribute("loop");
  video.pause();
  video.controls = true;
}
