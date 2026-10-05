// The /demo/booking-assistant page's conversation logic. Presented as an
// actual chat (not a form wizard) -- see that page's own comment on why.
// External file (not an inline <script>) for the same
// Content-Security-Policy reason voice-receptionist.js is -- see that
// file's own comment on this. postJSON/formatSlot come from
// widget-common.js, loaded before this file.
const { apiUrl } = document.currentScript.dataset;
const { postJSON, formatSlot, lang } = window.MlxWidget;

// Every visible string, per site language (QA 2026-10-05, BUG-05: the
// Norwegian site's booking demo greeted and replied in English).
const STRINGS = {
  en: {
    greeting: "Hi! What would you like to book?",
    checking: "Let me check what's open…",
    noAvailability: "No open times in that window — try a different day or date range.",
    noAvailabilityPart: (part) => `No open ${part} times in that window. Try another day, or a different time of day.`,
    parts: { morning: "morning", afternoon: "afternoon", evening: "evening" },
    slotsIntro: (minutes, type) => `Here's what's open for a ${minutes}-minute ${type}:`,
    askName: "Great — what's your name?",
    namePlaceholder: "Your name",
    askEmail: "And what's the best email for the calendar invite?",
    booking: "Booking that in…",
    conflict: "Sorry, that time was just taken. Let's find you another — what would you like to book?",
    booked: (slot, email) =>
      `You're booked! ${slot} — a calendar invite is on its way to ${email}. Want to book something else? Just tell me what and when.`,
    pickSlot: "Pick one of the times above, or tell me a different day to check.",
    closing: "Sounds good — thanks for stopping by! Come back anytime you'd like to book something.",
    error: "Sorry, something went wrong reaching the server. Please try again.",
    placeholder: "e.g. a 30 minute consultation next Tuesday afternoon",
  },
  no: {
    greeting: "Hei! Hva vil du bestille?",
    checking: "Jeg sjekker hva som er ledig …",
    noAvailability: "Ingen ledige tider i den perioden — prøv en annen dag eller periode.",
    noAvailabilityPart: (part) => `Ingen ledige tider på ${part} i den perioden. Prøv en annen dag eller en annen tid på dagen.`,
    parts: { morning: "formiddagen", afternoon: "ettermiddagen", evening: "kvelden" },
    slotsIntro: (minutes, type) => `Dette er ledig for ${type} på ${minutes} minutter:`,
    askName: "Flott — hva heter du?",
    namePlaceholder: "Navnet ditt",
    askEmail: "Og hvilken e-postadresse skal kalenderinvitasjonen sendes til?",
    booking: "Jeg bestiller …",
    conflict: "Beklager, den tiden ble nettopp tatt. Vi finner en annen — hva vil du bestille?",
    booked: (slot, email) =>
      `Du er booket! ${slot} — en kalenderinvitasjon er på vei til ${email}. Vil du bestille noe mer? Bare si hva og når.`,
    pickSlot: "Velg en av tidene over, eller si en annen dag jeg skal sjekke.",
    closing: "Den er grei — takk for besøket! Kom gjerne tilbake når du vil bestille noe.",
    error: "Beklager, noe gikk galt i kontakten med serveren. Prøv igjen.",
    placeholder: "f.eks. en konsultasjon på 30 minutter neste tirsdag ettermiddag",
  },
};
const T = STRINGS[lang()];

const transcriptEl = document.getElementById("transcript");
const slotsWrap = document.getElementById("slotsWrap");
const composerForm = document.getElementById("composerForm");
const composerInput = document.getElementById("composerInput");
const composerSend = document.getElementById("composerSend");

// The browser already knows the visitor's real timezone precisely -- sent
// straight to the server rather than asked of the LLM (see
// agents_booking.py's _RequestBookingBody comment on why parsing a
// timezone out of free text is a bad idea).
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

// Same bubble shape /demo/voice-receptionist's transcript uses, for a
// consistent feel across both live demos. "visitor"/"ai" here, not
// "caller"/"agent" -- same idea, different words for a text chat.
function addBubble(who, text) {
  const p = document.createElement("p");
  const base = "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-snug";
  if (who === "visitor") {
    p.className = base + " brand-gradient self-end rounded-br-md text-white";
  } else {
    p.className = base + " self-start rounded-bl-md bg-slate-100 text-slate-800";
  }
  p.textContent = text;
  transcriptEl.appendChild(p);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  return p;
}

// Small conversation state machine -- which chat turn the NEXT typed
// message answers. Slot selection happens via the buttons in slotsWrap,
// not the composer; everything else (the initial request, name, email)
// flows through it as normal chat turns.
let stage = "describe"; // "describe" | "awaiting_slot" | "awaiting_name" | "awaiting_email"
let meetingType = "appointment";
let chosenSlot = null;
let visitorName = "";
let visitorEmail = "";

// This page's whole purpose is booking -- there's no general chat fallback
// here (unlike the real product's Chat Widget, which mixes booking with
// normal RAG-grounded Q&A) -- so with no closing-words check, a decline or
// goodbye typed right after "Want to book something else?" got treated as
// a fresh (and nonsensical) booking description, immediately re-asking
// "what would you like to schedule?" again. Confirmed live with "no
// thanks", "bye", "goodbye" -- and "no its okay", which an earlier
// exact-match word list missed entirely (natural declines rarely come as
// just one of a fixed set of exact phrases). Patterns instead of an exact
// list, same spirit as the backend's own rag/pipeline.py _detect_intent,
// since this page never calls an LLM for anything except an actual
// booking description.
const CLOSING_PATTERNS = [
  /^no\b/, // "no", "no thanks", "no its okay", "no I'm good", ...
  /\bnope\b/,
  /\bnah\b/,
  /\bi'?m (all )?good\b/,
  /\ball set\b/,
  /\bnothing else\b/,
  /\bthat'?s (all|it)\b/,
  /\bi'?m done\b/,
  /\bbye\b/,
  /\bgoodbye\b/,
  /\bsee you\b/,
  /\bcya\b/,
  // Norwegian: "nei", "nei takk", "ha det", "det var alt", ...
  /^nei\b/,
  /\bha det\b/,
  /\bdet var alt\b/,
  /\bdet er greit\b/,
];

function looksLikeClosing(text) {
  const normalized = text.trim().toLowerCase();
  return CLOSING_PATTERNS.some((pattern) => pattern.test(normalized));
}

function showSlots(slots) {
  slotsWrap.innerHTML = "";
  slotsWrap.classList.remove("hidden");
  slotsWrap.classList.add("flex");
  for (const slot of slots) {
    const btn = document.createElement("button");
    btn.className =
      "w-full rounded-xl border border-slate-200 px-3 py-2 text-left text-sm font-medium text-slate-700 transition-colors hover:border-violet-400 hover:bg-violet-50";
    btn.textContent = formatSlot(slot.start);
    btn.addEventListener("click", () => pickSlot(slot));
    slotsWrap.appendChild(btn);
  }
}

function hideSlots() {
  slotsWrap.classList.add("hidden");
  slotsWrap.classList.remove("flex");
  slotsWrap.innerHTML = "";
}

function pickSlot(slot) {
  chosenSlot = slot;
  hideSlots();
  addBubble("visitor", formatSlot(slot.start));
  addBubble("ai", T.askName);
  stage = "awaiting_name";
  composerInput.placeholder = T.namePlaceholder;
}

async function handleDescribe(text) {
  addBubble("ai", T.checking);
  const result = await postJSON(apiUrl, "/api/agents/booking/request", { message: text, timezone, lang: lang() });
  meetingType = result.meeting_type || "appointment";

  if (result.status === "clarification_needed") {
    addBubble("ai", result.clarification_question);
    return;
  }
  if (result.status === "no_availability") {
    // QA 2026-10-05 (BUG-06): say so when the asked-for part of the day is full.
    const part = T.parts[result.time_of_day];
    addBubble("ai", part ? T.noAvailabilityPart(part) : T.noAvailability);
    return;
  }
  addBubble("ai", T.slotsIntro(result.duration_minutes, meetingType));
  showSlots(result.slots);
  stage = "awaiting_slot";
}

async function handleConfirm() {
  addBubble("ai", T.booking);
  const result = await postJSON(apiUrl, "/api/agents/booking/confirm", {
    name: visitorName,
    email: visitorEmail,
    start: chosenSlot.start,
    end: chosenSlot.end,
    timezone,
    meeting_type: meetingType,
  });

  if (result.status === "conflict") {
    addBubble("ai", T.conflict);
    stage = "describe";
    composerInput.placeholder = T.placeholder;
    chosenSlot = null;
    return;
  }

  addBubble("ai", T.booked(formatSlot(chosenSlot.start), visitorEmail));
  stage = "describe";
  composerInput.placeholder = T.placeholder;
  chosenSlot = null;
  visitorName = "";
  visitorEmail = "";
}

composerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = composerInput.value.trim();
  if (!text) return;
  composerInput.value = "";
  addBubble("visitor", text);

  composerInput.disabled = true;
  composerSend.disabled = true;
  try {
    if (stage === "describe" && looksLikeClosing(text)) {
      addBubble("ai", T.closing);
    } else if (stage === "describe") {
      await handleDescribe(text);
    } else if (stage === "awaiting_slot") {
      addBubble("ai", T.pickSlot);
    } else if (stage === "awaiting_name") {
      visitorName = text;
      addBubble("ai", T.askEmail);
      stage = "awaiting_email";
      composerInput.placeholder = "you@example.com";
    } else if (stage === "awaiting_email") {
      visitorEmail = text;
      await handleConfirm();
    }
  } catch (err) {
    console.error("Booking demo error:", err);
    addBubble("ai", T.error);
  } finally {
    composerInput.disabled = false;
    composerSend.disabled = false;
    composerInput.focus();
  }
});

addBubble("ai", T.greeting);
