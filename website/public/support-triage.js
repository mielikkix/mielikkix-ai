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
// widget.js bubble does. postJSON comes from widget-common.js, loaded
// before this file.
const { apiUrl } = document.currentScript.dataset;
const { postJSON } = window.MlxWidget;

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

// Maps the response's own declined/escalated/suggest_booking_flow flags (see
// app/api/agents_support.py's _ChatMessageResponse) onto a short, honest
// label -- these are exactly the three outcomes handle_chat_message() in
// support_service.py can produce for a given message, in the same order
// it checks them.
function tagFor(result) {
  if (result.suggest_booking_flow) {
    return { text: "📅 Booking request detected -- handed off to Booking Assistant", className: "text-violet-600" };
  }
  if (result.declined) {
    return { text: "🛡️ Declined -- outside what this assistant will do", className: "text-slate-500" };
  }
  if (result.escalated) {
    return { text: "🚩 Not confident enough -- escalated to a real person", className: "text-amber-600" };
  }
  return { text: "✓ Answered confidently from Mielikkix's own docs", className: "text-emerald-600" };
}

// Escalated with no way to reach the visitor yet (needs_contact): ask for an
// email right in the transcript, posted to /chat/contact, which attaches it to
// the ticket and re-sends the escalation email to the team.
function addContactForm() {
  const form = document.createElement("form");
  form.className = "flex max-w-[85%] gap-2";
  const input = document.createElement("input");
  input.type = "email";
  input.required = true;
  input.autocomplete = "email";
  input.placeholder = "you@example.com";
  input.setAttribute("aria-label", "Your email address");
  input.className = "min-w-0 flex-1 rounded-full border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-violet-400";
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Send";
  button.className = "brand-gradient rounded-full px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50";
  form.append(input, button);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    button.disabled = true;
    try {
      const result = await postJSON(apiUrl, "/api/agents/support/chat/contact", { session_id: sessionId, email: input.value.trim() });
      form.remove();
      addBubble("ai", result.reply);
    } catch (err) {
      console.error("Support Triage contact error:", err);
      button.disabled = false;
      input.setCustomValidity("Please check the email address and try again.");
      input.reportValidity();
      input.addEventListener("input", () => input.setCustomValidity(""), { once: true });
    }
  });
  transcriptEl.appendChild(form);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  input.focus();
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
    const result = await postJSON(apiUrl, "/api/agents/support/chat/message", { session_id: sessionId, message: text });
    addBubble("ai", result.reply, tagFor(result));
    if (result.needs_contact && !transcriptEl.querySelector("form")) addContactForm();
  } catch (err) {
    console.error("Support Triage demo error:", err);
    addBubble("ai", "Sorry, something went wrong reaching the server. Please try again.");
  } finally {
    composerInput.disabled = false;
    composerSend.disabled = false;
    if (!transcriptEl.querySelector("form")) composerInput.focus();
  }
});

addBubble("ai", "Hi! Ask me anything about Mielikkix, or try something off-topic to see what happens.");
