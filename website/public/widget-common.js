// Small helpers shared by every website/public/*.js conversation widget
// (voice-receptionist.js, booking-assistant.js, support-triage.js,
// support-chat-widget.js). Exposed as window.MlxWidget rather than an ES
// module, since these are all loaded as plain <script src> tags (not
// type="module") for the same Content-Security-Policy reason each of
// those files' own comment explains -- a <script type="module"> import
// graph would work too, but every file already assumes a global scope.
//
// Loaded via its own <script src="/widget-common.js"> tag, before the
// page-specific script that uses it.
window.MlxWidget = (function () {
  async function postJSON(apiUrl, path, body) {
    const resp = await fetch(`${apiUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `${path} returned ${resp.status}`);
    return data;
  }

  function formatSlot(startISO) {
    return new Date(startISO).toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return { postJSON, formatSlot };
})();
