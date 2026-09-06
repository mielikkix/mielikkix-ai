// The /demo/whatsapp-concierge page's conversation logic. External file
// (not an inline <script>) for the same Content-Security-Policy reason
// voice-receptionist.js/booking-assistant.js/support-triage.js already are
// -- see any of those files' own comment on this.
//
// Unlike those three, this one talks to NO backend at all: Mielikkix's
// WhatsApp Business number is still pending Meta's approval, so there is
// no apps/api/app/api/agents_whatsapp.py route to call yet. Every "reply"
// here is looked up from CANNED_REPLIES below, entirely client-side, so
// this file has none of the postJSON/apiUrl plumbing the other three
// demo scripts have. Once the number is live, this becomes a real
// integration and this whole file gets replaced the way support-triage.js
// or booking-assistant.js already talk to their real routes.

const chatAreaEl = document.getElementById("chatArea");
const transcriptEl = document.getElementById("transcript");
const quickRepliesEl = document.getElementById("quickReplies");
const statusLineEl = document.getElementById("statusLine");
const composerForm = document.getElementById("composerForm");
const composerInput = document.getElementById("composerInput");
const micIcon = document.getElementById("micIcon");
const sendIcon = document.getElementById("sendIcon");

// Keyword -> canned reply. Checked in order, first match wins -- same
// "confident answer, otherwise fall back" shape support-triage.js uses,
// just without a real classifier behind it.
const CANNED_REPLIES = [
  { keywords: ["hour", "open", "close", "time"], reply: "We're open Mon-Sat, 9:00-18:00, and closed Sundays! 😊" },
  { keywords: ["book", "appointment", "schedule", "reserve", "slot"], reply: "I can help with that! What day works best for you, and what service are you after?" },
  { keywords: ["price", "pricing", "cost", "how much", "fee", "rate"], reply: "Our starting rate is 450 kr -- happy to send over the full price list if you'd like!" },
  { keywords: ["location", "address", "where"], reply: "We're at Storgata 12, Oslo -- right by the tram stop! 📍" },
  { keywords: ["human", "person", "agent", "staff", "someone", "manager"], reply: "Of course -- connecting you with a real team member now. Someone will reply here shortly!" },
  { keywords: ["thank", "thanks"], reply: "You're very welcome! Let me know if there's anything else I can help with." },
  // Plain acknowledgements ("ok", "okay", "sounds good", ...) -- without
  // this, a visitor just confirming what Mieli said fell through to
  // FALLBACK_REPLY's "I've passed that along to the team" line, which
  // reads as broken when nothing was actually asked. "ok" is a 2-letter
  // substring match, so this MUST stay after the booking rule above: "ok"
  // is itself a substring of "book"/"booking", and first-match-wins means
  // any message that also mentions booking needs the booking rule to fire
  // first, not this one.
  { keywords: ["ok", "okay", "alright", "sounds good", "got it", "sure thing", "perfect", "cool"], reply: "Great, glad that helps! Let me know if there's anything else I can help with. 😊" },
  { keywords: ["bye", "goodbye", "see you", "have a good", "cya"], reply: "Bye for now! 👋 Reach out anytime -- we're just a message away." },
];
const FALLBACK_REPLY =
  "Got it -- I've passed that along to the team and someone will follow up here shortly. In the meantime, I can help with our hours, pricing, location, or booking an appointment.";

const QUICK_REPLIES = ["What are your hours?", "Can I book an appointment?", "What's the pricing?", "I'd like to talk to a person"];

function timeNow() {
  return new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

// Auto-scrolls only the phone's own chat viewport (#chatArea, which has its
// own overflow-y-auto) down to the newest bubble -- like a real WhatsApp
// screen keeping pace with the conversation. Deliberately scoped to this
// one scrollable element, not the surrounding website page: an earlier
// version called composerForm.scrollIntoView(), which scrolled the whole
// page and yanked the visitor's position around outside the phone -- not
// what "auto-scroll" should mean here.
//
// Instant assignment, not scrollTo({behavior:"smooth"}): the typing
// indicator and the reply that replaces it fire two scroll requests a
// few hundred ms apart, and a second smooth scroll issued before the
// first finishes gets interrupted by Chrome rather than queued -- net
// effect, confirmed by measuring scrollTop after a burst of replies, was
// the view staying stuck at the top instead of following the newest
// message. Instant scrollTop has no animation to interrupt.
function scrollChatToBottom() {
  chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
}

function ticksSVG() {
  const span = document.createElement("span");
  span.className = "ticks ml-0.5 inline-flex shrink-0 items-center";
  span.style.color = "rgba(0,0,0,.45)";
  span.innerHTML =
    '<svg class="h-[13px] w-[17px]" viewBox="0 0 16 11" fill="none">' +
    '<path class="tick1" d="M1 5.5 4 8.5 9.5 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<path class="tick2" d="M5.5 5.5 8.5 8.5 14 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" style="opacity:0"/>' +
    "</svg>";
  return span;
}

function setTicksStatus(bubble, status) {
  const ticks = bubble && bubble.querySelector(".ticks");
  if (!ticks) return;
  const tick2 = ticks.querySelector(".tick2");
  if (status === "sent") {
    tick2.style.opacity = "0";
    ticks.style.color = "rgba(0,0,0,.45)";
  } else if (status === "delivered") {
    tick2.style.opacity = "1";
    ticks.style.color = "rgba(0,0,0,.45)";
  } else if (status === "read") {
    tick2.style.opacity = "1";
    ticks.style.color = "#53bdeb";
  }
}

// Bubble shape mirrors the other three demos' addBubble() (rounded-2xl,
// one corner squared toward the sender), colored WhatsApp-style instead
// of brand-violet: light green for the visitor's own sent messages,
// white for Mieli's -- same convention a customer's own WhatsApp app uses.
function addMessage(who, text) {
  const row = document.createElement("div");
  row.className = "flex " + (who === "visitor" ? "justify-end" : "justify-start");

  const bubble = document.createElement("div");
  bubble.className =
    "max-w-[80%] rounded-lg px-2.5 py-1.5 shadow-sm " +
    (who === "visitor" ? "rounded-tr-sm bg-[#d9fdd3]" : "rounded-tl-sm bg-white");

  const p = document.createElement("p");
  p.className = "whitespace-pre-wrap text-[13.5px] leading-snug text-[#111b21]";
  p.textContent = text;
  bubble.appendChild(p);

  const meta = document.createElement("div");
  meta.className = "mt-0.5 flex items-center justify-end gap-0.5";
  const time = document.createElement("span");
  time.className = "text-[10px] text-black/45";
  time.textContent = timeNow();
  meta.appendChild(time);
  if (who === "visitor") meta.appendChild(ticksSVG());
  bubble.appendChild(meta);

  row.appendChild(bubble);
  transcriptEl.appendChild(row);
  scrollChatToBottom();
  return bubble;
}

let typingRow = null;
function showTyping() {
  typingRow = document.createElement("div");
  typingRow.className = "flex justify-start";
  const bubble = document.createElement("div");
  bubble.className = "flex items-center gap-1 rounded-lg rounded-tl-sm bg-white px-3 py-2.5 shadow-sm";
  [0, 150, 300].forEach((delay) => {
    const dot = document.createElement("span");
    dot.className = "h-1.5 w-1.5 animate-bounce rounded-full bg-black/40";
    dot.style.animationDelay = delay + "ms";
    bubble.appendChild(dot);
  });
  typingRow.appendChild(bubble);
  transcriptEl.appendChild(typingRow);
  scrollChatToBottom();
}
function hideTyping() {
  if (typingRow) {
    typingRow.remove();
    typingRow = null;
  }
}

function matchReply(text) {
  const lower = text.toLowerCase();
  const hit = CANNED_REPLIES.find((entry) => entry.keywords.some((kw) => lower.includes(kw)));
  return hit ? hit.reply : FALLBACK_REPLY;
}

function renderQuickReplies() {
  quickRepliesEl.innerHTML = "";
  QUICK_REPLIES.forEach((label) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className =
      "rounded-full border border-[#008069]/30 bg-white px-3 py-1.5 text-[11.5px] font-medium text-[#008069] transition-colors hover:bg-[#008069]/10";
    chip.textContent = label;
    chip.addEventListener("click", () => sendMessage(label));
    quickRepliesEl.appendChild(chip);
  });
  // #quickReplies sits outside #chatArea but shares the same fixed-height
  // flex column: sendMessage() clears it to 0 height for the whole
  // typing/reply exchange, which lets #chatArea (flex-1) balloon into that
  // freed space, so the scrollChatToBottom() call inside addMessage("ai", ...)
  // lands against that temporarily-taller box. The moment these chips come
  // back, #chatArea snaps back down to its real height and that earlier
  // scroll position is now short of the true bottom. Re-scrolling here,
  // after layout has settled back to its real size, is what actually keeps
  // Mieli's reply in view.
  scrollChatToBottom();
}

function updateSendIcon() {
  const hasText = composerInput.value.trim().length > 0;
  micIcon.classList.toggle("hidden", hasText);
  sendIcon.classList.toggle("hidden", !hasText);
}
composerInput.addEventListener("input", updateSendIcon);

function sendMessage(text) {
  // Cleared here and never re-rendered below: the chips are onboarding
  // hints for a blank conversation ("not sure what to ask? try one of
  // these"), not a persistent menu. Once a visitor has sent one real
  // message they're already typing their own questions, so refreshing a
  // fresh set of suggestions after every single reply just clutters a
  // real WhatsApp-style thread with UI that a real WhatsApp Business
  // number would never show.
  quickRepliesEl.innerHTML = "";
  const visitorBubble = addMessage("visitor", text);

  setTimeout(() => setTicksStatus(visitorBubble, "delivered"), 400);

  statusLineEl.textContent = "typing...";
  showTyping();
  const delay = 900 + Math.random() * 700;
  setTimeout(() => {
    hideTyping();
    setTicksStatus(visitorBubble, "read");
    addMessage("ai", matchReply(text));
    statusLineEl.textContent = "online";
  }, delay);
}

composerForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = composerInput.value.trim();
  if (!text) return;
  composerInput.value = "";
  updateSendIcon();
  sendMessage(text);
});

// Scripted opener, played once on load -- gives the phone something to
// show immediately instead of an empty chat.
setTimeout(() => {
  statusLineEl.textContent = "typing...";
  showTyping();
  setTimeout(() => {
    hideTyping();
    addMessage("ai", "Hi there! 👋 Thanks for messaging Mielikkix. I'm Mieli, your AI concierge -- I can help with hours, bookings, pricing, or anything else. What can I do for you?");
    statusLineEl.textContent = "online";
    renderQuickReplies();
  }, 1100);
}, 500);
