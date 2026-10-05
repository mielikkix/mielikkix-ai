// The /demo/voice-receptionist page's conversation logic. Kept as an
// external file (rather than an inline/bundled <script> in the .astro
// page) so it isn't blocked by the site's Content-Security-Policy, which
// has no 'unsafe-inline' for script-src -- see i18n-guard.js for the same
// pattern. apiUrl comes from this script tag's own data-api-url attribute
// (set at build time by the .astro page from PUBLIC_API_URL) rather than
// Astro's define:vars, since define:vars only works on is:inline scripts,
// which is exactly what triggers the CSP block in the first place.
// postJSON comes from widget-common.js, loaded before this file.
const { apiUrl } = document.currentScript.dataset;
const { postJSON, lang } = window.MlxWidget;

// Page chrome per site language (QA 2026-10-05, BUG-07: the Norwegian site
// greeted in English with English labels). The spoken replies themselves
// come from the server, in the call's language.
const STRINGS = {
  en: {
    pill: { idle: "Speak now", connecting: "Connecting you to Mieli...", active: "Speak with Mieli" },
    getReady: "Get ready...",
    listening: "Listening...",
    thinking: "Thinking...",
    speaking: "Speaking...",
    connecting: "Connecting...",
    serverError: "Sorry, something went wrong reaching the server.",
    startFailed: "Couldn't reach the server -- check your connection and try again.",
    ended: "Call ended -- click Speak now to talk again",
    micProblem: "Mic problem: ",
    seeConsole: "see the browser console (F12) for details.",
    noNorwegianVoice:
      "Your browser has no Norwegian voice installed, so Mieli reads the Norwegian replies with its default voice. The text below is always correct.",
    errors: {
      "not-allowed": "Microphone permission was denied/blocked. Click the mic/lock icon in the address bar and allow it.",
      "audio-capture": "No microphone was found. Check a mic is connected and selected as the default input device.",
      network: "Couldn't reach the speech-recognition service. Check your internet connection.",
      "service-not-allowed": "The browser blocked access to its speech-recognition service.",
      aborted: "Recognition was interrupted before it finished.",
    },
  },
  no: {
    pill: { idle: "Snakk nå", connecting: "Kobler deg til Mieli ...", active: "Snakk med Mieli" },
    getReady: "Gjør deg klar ...",
    listening: "Lytter ...",
    thinking: "Tenker ...",
    speaking: "Snakker ...",
    connecting: "Kobler til ...",
    serverError: "Beklager, noe gikk galt i kontakten med serveren.",
    startFailed: "Fikk ikke kontakt med serveren -- sjekk tilkoblingen og prøv igjen.",
    ended: "Samtalen er avsluttet -- klikk Snakk nå for å snakke igjen",
    micProblem: "Problem med mikrofonen: ",
    seeConsole: "se nettleserkonsollen (F12) for detaljer.",
    noNorwegianVoice:
      "Nettleseren din har ingen norsk stemme installert, så Mieli leser de norske svarene med standardstemmen. Teksten nedenfor er alltid riktig.",
    errors: {
      "not-allowed": "Tilgang til mikrofonen ble avvist. Klikk på mikrofon- eller hengelåsikonet i adressefeltet og gi tilgang.",
      "audio-capture": "Fant ingen mikrofon. Sjekk at en mikrofon er koblet til og valgt som standard inndataenhet.",
      network: "Fikk ikke kontakt med talegjenkjenningstjenesten. Sjekk internettforbindelsen.",
      "service-not-allowed": "Nettleseren blokkerte tilgang til talegjenkjenningstjenesten.",
      aborted: "Gjenkjenningen ble avbrutt før den var ferdig.",
    },
  },
};
const T = STRINGS[lang()];
const voiceNoticeEl = document.getElementById("voiceNotice");

const avatarRing = document.getElementById("avatarRing");
const waveformEl = document.getElementById("waveform");
const waveformBars = document.querySelectorAll("#waveform span");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const pillBtn = document.getElementById("pillBtn");
const pillLabel = document.getElementById("pillLabel");
const pillMic = document.getElementById("pillMic");
const hangupWrap = document.getElementById("hangupWrap");
const hangupBtn = document.getElementById("hangupBtn");
const unsupportedEl = document.getElementById("unsupported");

// The pill button is the page's single call-to-action: "Speak now" (idle,
// clickable) -> "Connecting you to Mieli..." (mid-handshake, mic hidden,
// disabled) -> "Speak with Mieli" (call live; the detailed Listening/
// Thinking/Speaking status and waveform take over below it, and "End call"
// appears as its own control instead of overloading the pill).
const PILL_LABELS = T.pill;

function setPill(state) {
  pillLabel.textContent = PILL_LABELS[state];
  pillMic.classList.toggle("hidden", state === "connecting");
  pillBtn.disabled = state !== "idle";
  const showDetail = state === "active";
  waveformEl.classList.toggle("hidden", !showDetail);
  waveformEl.classList.toggle("flex", showDetail);
  hangupWrap.classList.toggle("hidden", !showDetail);
  hangupWrap.classList.toggle("flex", showDetail);
}

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let callSid = null;
let active = false;
// "en" or "no" -- mirrors the server's own per-call _call_language (see
// agents_voice.py's _DevReply.language). The server decides WHETHER this
// call has switched to Norwegian (from the caller's own speech); this
// variable just drives which language THIS PAGE listens/speaks in next,
// so the two stay in lockstep turn by turn.
let currentLanguage = "en";

const STATE_COLORS = { idle: "text-slate-500", listening: "text-emerald-600", thinking: "text-amber-600", speaking: "text-violet-600" };

function setState(state, text) {
  statusEl.textContent = text;
  statusEl.className = "mb-6 text-sm font-semibold " + (STATE_COLORS[state] || STATE_COLORS.idle);
  const animate = state === "listening" || state === "speaking";
  avatarRing.style.animation = animate ? "pulse-ring 1.4s ease-out infinite" : "none";
  waveformBars.forEach((bar, i) => {
    bar.style.animation = animate ? `wave 0.9s ease-in-out ${i * 0.1}s infinite` : "none";
    bar.style.background = state === "listening" ? "#1a7f37" : "#8b5cf6";
    if (!animate) bar.style.height = "6px";
  });
}

function logLine(who, text) {
  const p = document.createElement("p");
  const base = "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-snug";
  if (who === "caller") {
    p.className = base + " brand-gradient self-end rounded-br-md text-white";
  } else if (who === "error") {
    p.className = base + " self-center rounded-lg bg-red-50 font-semibold text-red-700";
    text = T.micProblem + text;
  } else {
    p.className = base + " self-start rounded-bl-md bg-slate-100 text-slate-800";
  }
  p.textContent = text;
  transcriptEl.appendChild(p);
  transcriptEl.style.display = "flex";
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  return p; // so callers can update this exact bubble later (see heard_as correction)
}

function getVoicesAsync() {
  return new Promise((resolve) => {
    const existing = window.speechSynthesis.getVoices();
    if (existing.length) return resolve(existing);
    window.speechSynthesis.onvoiceschanged = () => resolve(window.speechSynthesis.getVoices());
  });
}

function pickFemaleVoice(voices) {
  const patterns = /female|zira|hazel|susan|samantha|victoria|karen|moira|tessa|fiona|aria|jenny/i;
  return voices.find((v) => patterns.test(v.name)) || null;
}

// Norwegian voice availability varies a lot by OS/browser (often just one,
// sometimes none) -- unlike pickFemaleVoice, this can't afford to also
// filter by name pattern, or it'd come up empty on browsers that only ship
// one Norwegian voice with an unremarkable name. `nb`/`no` covers both
// Bokmål ("nb-NO") and the older generic "no-NO" tag some engines still use.
function pickNorwegianVoice(voices) {
  return voices.find((v) => /^(nb|no)\b/i.test(v.lang)) || null;
}

let femaleVoice = null;
let norwegianVoice = null;
getVoicesAsync().then((voices) => {
  femaleVoice = pickFemaleVoice(voices);
  norwegianVoice = pickNorwegianVoice(voices);
});

function speak(text) {
  return new Promise((resolve) => {
    setState("speaking", T.speaking);
    const utterance = new SpeechSynthesisUtterance(text);
    // Falls back to the browser's default voice (reading Norwegian text
    // with an English accent) if this browser/OS has no Norwegian voice
    // installed at all -- still understandable, and better than silently
    // speaking the wrong language's voice for English text instead.
    // The voice list can still be loading on the first reply.
    if (!norwegianVoice) norwegianVoice = pickNorwegianVoice(window.speechSynthesis.getVoices());
    const voice = currentLanguage === "no" ? norwegianVoice : femaleVoice;
    if (voice) utterance.voice = voice;
    // Say so instead of silently reading Norwegian with an English voice.
    if (currentLanguage === "no" && !norwegianVoice) {
      voiceNoticeEl.textContent = T.noNorwegianVoice;
      voiceNoticeEl.classList.remove("hidden");
    }
    utterance.lang = currentLanguage === "no" ? "nb-NO" : "en-US";
    utterance.onend = resolve;
    utterance.onerror = resolve;
    window.speechSynthesis.speak(utterance);
  });
}

function listenOnce() {
  return new Promise((resolve) => {
    // "Get ready..." here, not "Listening..." -- recognizer.start() is
    // still ~300ms away (see below), and showing "Listening..." before
    // the mic is actually capturing was making people start talking
    // right away, clipping the first word or two of what they said.
    // The status only switches to "Listening..." once recognition has
    // genuinely started (onstart, below).
    setState("listening", T.getReady);
    recognizer = new SpeechRecognitionCtor();
    recognizer.lang = currentLanguage === "no" ? "nb-NO" : "en-US";
    recognizer.continuous = false;
    recognizer.interimResults = false;
    recognizer.maxAlternatives = 1;

    let resolved = false;
    const finish = (transcript, error) => {
      if (resolved) return;
      resolved = true;
      resolve({ transcript, error: error || null });
    };

    recognizer.onstart = () => setState("listening", T.listening);
    recognizer.onresult = (event) => finish(event.results[0][0].transcript);
    recognizer.onerror = (event) => {
      console.error("SpeechRecognition error:", event.error);
      finish("", event.error === "no-speech" ? null : event.error);
    };
    recognizer.onend = () => finish("");
    setTimeout(() => recognizer.start(), 300);
  });
}

const ERROR_HINTS = T.errors;

// These won't resolve themselves by just trying again -- a denied mic
// permission or missing hardware stays denied/missing on every retry, so
// looping on them just spams the transcript with the same error forever
// instead of actually recovering. Stop the call instead; only genuinely
// transient errors (e.g. "network", "aborted") retry via the loop below.
const FATAL_RECOGNITION_ERRORS = new Set(["not-allowed", "audio-capture", "service-not-allowed"]);

async function conversationLoop() {
  while (active) {
    const { transcript, error } = await listenOnce();
    if (!active) return;

    if (error) {
      logLine("error", `${error} -- ${ERROR_HINTS[error] || T.seeConsole}`);
      if (FATAL_RECOGNITION_ERRORS.has(error)) {
        hangUp();
        return;
      }
      continue;
    }

    const callerBubble = transcript ? logLine("caller", transcript) : null;

    setState("thinking", T.thinking);
    let reply, ended = false, heard_as = null;
    try {
      const result = await postJSON(apiUrl, "/api/agents/voice/dev/gather", { call_sid: callSid, speech: transcript });
      ({ reply, ended, heard_as } = result);
      // Update BEFORE speak() below, so a turn that just switched languages
      // (per the server's own _call_language latch) speaks its own reply
      // in the new language immediately, not one turn late.
      if (result.language) currentLanguage = result.language;
    } catch (err) {
      reply = T.serverError;
    }
    if (!active) return;
    // If the server recognized this as a known mishearing of
    // "Mielikkix", visibly correct the caller's own bubble to show
    // what was actually meant, live -- the same recognized text is
    // still what was sent for retrieval either way (see
    // agents_voice.py's _anchor_query_for_retrieval, which is separate
    // and always general-purpose, not tied to this list).
    if (callerBubble && heard_as) callerBubble.textContent = heard_as;
    logLine("agent", reply);
    await speak(reply);
    if (ended) {
      // Caller said something like "bye", or went quiet for too long --
      // the server already decided the call is over; end it here too
      // instead of listening again, same as clicking Hang Up.
      hangUp();
      return;
    }
  }
}

async function startCall() {
  callSid = crypto.randomUUID();
  transcriptEl.innerHTML = "";
  active = true;
  // A call starts in the site's language -- see agents_voice.py's _start_call.
  currentLanguage = lang();
  voiceNoticeEl.classList.add("hidden");
  setPill("connecting");
  setState("thinking", T.connecting);

  // Unlike the /gather call in conversationLoop (which falls back to an
  // apology reply and keeps going, since the call is already underway by
  // then), a failure here means the call never actually started -- there's
  // no greeting and no call_sid registered server-side to continue against.
  // Reset to idle instead of leaving the pill stuck on "Connecting..."
  // forever with no feedback.
  let reply;
  try {
    ({ reply } = await postJSON(apiUrl, "/api/agents/voice/dev/start", { call_sid: callSid, language: currentLanguage }));
  } catch (err) {
    console.error("Failed to start call:", err);
    active = false;
    setPill("idle");
    setState("idle", T.startFailed);
    return;
  }

  setPill("active");
  logLine("agent", reply);
  await speak(reply);

  conversationLoop();
}

function hangUp() {
  active = false;
  window.speechSynthesis.cancel();
  if (recognizer) {
    try { recognizer.stop(); } catch (e) {}
  }
  setPill("idle");
  setState("idle", T.ended);
}

if (!SpeechRecognitionCtor) {
  unsupportedEl.classList.remove("hidden");
  pillBtn.disabled = true;
} else {
  pillBtn.addEventListener("click", startCall);
  hangupBtn.addEventListener("click", hangUp);
}
