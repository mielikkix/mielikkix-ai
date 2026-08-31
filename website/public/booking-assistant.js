// The /demo/booking-assistant page's conversation logic. Presented as an
// actual chat (not a form wizard) -- see that page's own comment on why.
// External file (not an inline <script>) for the same
// Content-Security-Policy reason voice-receptionist.js is -- see that
// file's own comment on this. postJSON/formatSlot come from
// widget-common.js, loaded before this file.
const { apiUrl } = document.currentScript.dataset;
const { postJSON, formatSlot } = window.MlxWidget;

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
  addBubble("ai", "Great — what's your name?");
  stage = "awaiting_name";
  composerInput.placeholder = "Your name";
}

async function handleDescribe(text) {
  addBubble("ai", "Let me check what's open…");
  const result = await postJSON(apiUrl, "/api/agents/booking/request", { message: text, timezone });
  meetingType = result.meeting_type || "appointment";

  if (result.status === "clarification_needed") {
    addBubble("ai", result.clarification_question);
    return;
  }
  if (result.status === "no_availability") {
    addBubble("ai", "No open times in that window — try a different day or date range.");
    return;
  }
  addBubble("ai", `Here's what's open for a ${result.duration_minutes}-minute ${meetingType}:`);
  showSlots(result.slots);
  stage = "awaiting_slot";
}

async function handleConfirm() {
  addBubble("ai", "Booking that in…");
  const result = await postJSON(apiUrl, "/api/agents/booking/confirm", {
    name: visitorName,
    email: visitorEmail,
    start: chosenSlot.start,
    end: chosenSlot.end,
    timezone,
    meeting_type: meetingType,
  });

  if (result.status === "conflict") {
    addBubble("ai", "Sorry, that time was just taken. Let's find you another — what would you like to book?");
    stage = "describe";
    composerInput.placeholder = "e.g. a 30 minute consultation next Tuesday afternoon";
    chosenSlot = null;
    return;
  }

  addBubble(
    "ai",
    `You're booked! ${formatSlot(chosenSlot.start)} — a calendar invite is on its way to ${visitorEmail}. ` +
      "Want to book something else? Just tell me what and when."
  );
  stage = "describe";
  composerInput.placeholder = "e.g. a 30 minute consultation next Tuesday afternoon";
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
      addBubble("ai", "Sounds good — thanks for stopping by! Come back anytime you'd like to book something.");
    } else if (stage === "describe") {
      await handleDescribe(text);
    } else if (stage === "awaiting_slot") {
      addBubble("ai", "Pick one of the times above, or tell me a different day to check.");
    } else if (stage === "awaiting_name") {
      visitorName = text;
      addBubble("ai", "And what's the best email for the calendar invite?");
      stage = "awaiting_email";
      composerInput.placeholder = "you@example.com";
    } else if (stage === "awaiting_email") {
      visitorEmail = text;
      await handleConfirm();
    }
  } catch (err) {
    console.error("Booking demo error:", err);
    addBubble("ai", "Sorry, something went wrong reaching the server. Please try again.");
  } finally {
    composerInput.disabled = false;
    composerSend.disabled = false;
    composerInput.focus();
  }
});

addBubble("ai", "Hi! What would you like to book?");
