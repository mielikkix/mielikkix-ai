// The /demo/support-triage page's conversation logic. External file (not
// an inline <script>) for the same Content-Security-Policy reason
// voice-receptionist.js/booking-assistant.js already are -- see either
// file's own comment on this.
//
// The whole point of this page (see its own comment): make Support
// Triage's actual behavior visible, not just "type a message, get a
// reply" like any generic chatbot. Every agent reply below gets a small
// tag showing what actually happened server-side -- confidently answered,
// escalated to a human, or handed off to Booking Assistant -- instead of
// leaving that decision invisible the way the sitewide support-chat-
// widget.js bubble does.
const { apiUrl } = document.currentScript.dataset;

const transcriptEl = document.getElementById("transcript");
const composerForm = document.getElementById("composerForm");
const composerInput = document.getElementById("composerInput");
const composerSend = document.getElementById("composerSend");

// One session per page load -- support_service.py's _get_or_create_ticket
// threads a whole conversation onto one Ticket by session_id (see that
// module's own comment), same convention support-chat-widget.js uses.
const sessionId = crypto.randomUUID();

// Same bubble shape /demo/voice-receptionist and /demo/booking-assistant
// use, for a consistent feel across all three live demos.
function addBubble(who, text, tag) {
  const wrap = document.createElement("div");
  wrap.className = "flex flex-col " + (who === "visitor" ? "items-end" : "items-start");

  const p = document.createElement("p");
  const base = "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-snug";
  p.className =
    who === "visitor"
      ? base + " brand-gradient rounded-br-md text-white"
      : base + " rounded-bl-md bg-slate-100 text-slate-800";
  p.textContent = text;
  wrap.appendChild(p);

  if (tag) {
    const tagEl = document.createElement("span");
    tagEl.className = "mt-1 max-w-[85%] text-[11px] font-medium " + tag.className;
    tagEl.textContent = tag.text;
    wrap.appendChild(tagEl);
  }

  transcriptEl.appendChild(wrap);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

// Maps the response's own escalated/suggest_booking_flow flags (see
// app/api/agents_support.py's _ChatMessageResponse) onto a short, honest
// label -- these are exactly the three outcomes handle_chat_message() in
// support_service.py can produce for a given message, in the same order
// it checks them.
function tagFor(result) {
  if (result.suggest_booking_flow) {
    return { text: "📅 Booking request detected -- handed off to Booking Assistant", className: "text-violet-600" };
  }
  if (result.escalated) {
    return { text: "🚩 Not confident enough -- escalated to a real person", className: "text-amber-600" };
  }
  return { text: "✓ Answered confidently from Mielikkix's own docs", className: "text-emerald-600" };
}

async function postJSON(path, body) {
  const resp = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `${path} returned ${resp.status}`);
  return data;
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
    const result = await postJSON("/api/agents/support/chat/message", { session_id: sessionId, message: text });
    addBubble("ai", result.reply, tagFor(result));
  } catch (err) {
    console.error("Support Triage demo error:", err);
    addBubble("ai", "Sorry, something went wrong reaching the server. Please try again.");
  } finally {
    composerInput.disabled = false;
    composerSend.disabled = false;
    composerInput.focus();
  }
});

addBubble("ai", "Hi! Ask me anything about Mielikkix, or try something off-topic to see what happens.");
