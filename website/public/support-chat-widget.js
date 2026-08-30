// Site-wide chat widget for mielikkix.ai itself, talking to Support Triage
// (app/api/agents_support.py), not the tenant-facing product Chat Widget
// (app.mielikkix.ai/widget.js) -- see apps/agents/support-triage/CLAUDE.md
// for why these are deliberately two different things. Replaces this site's
// previous embed of the generic product widget in Layout.astro: Support
// Triage's classify/answer/escalate-to-a-human behavior is the right fit
// for mielikkix.ai's OWN visitors, not the tenant-facing widget meant for a
// business's customers.
//
// External file, not an inline <script> -- same Content-Security-Policy
// reason every other website/public/*.js file is (see voice-receptionist.js
// or booking-assistant.js's own comment on this). Injects its own DOM/CSS
// rather than relying on Tailwind utility classes, since Tailwind's build
// only compiles classes it finds by scanning .astro/.tsx source at build
// time -- a class name that exists only in a public/ script's own
// runtime-created markup would have no matching CSS at all.
(function () {
  const { apiUrl } = document.currentScript.dataset;

  const SESSION_STORAGE_KEY = "mlx_support_session_id";
  function getSessionId() {
    let id = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_STORAGE_KEY, id);
    }
    return id;
  }

  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  const style = document.createElement("style");
  style.textContent = `
    #mlx-support-bubble {
      position: fixed; bottom: 20px; right: 20px; z-index: 2147483000;
      width: 56px; height: 56px; border-radius: 9999px; border: none; cursor: pointer;
      background-image: linear-gradient(135deg, #ff6b00 0%, #f5a623 100%);
      box-shadow: 0 8px 24px rgba(255, 107, 0, 0.35);
      display: flex; align-items: center; justify-content: center;
      color: #fff; font-size: 26px; line-height: 1;
      transition: transform 0.15s ease;
    }
    #mlx-support-bubble:hover { transform: scale(1.06); }
    #mlx-support-panel {
      position: fixed; bottom: 88px; right: 20px; z-index: 2147483000;
      width: min(360px, calc(100vw - 40px)); height: min(520px, calc(100vh - 140px));
      background: #fff; border-radius: 16px; box-shadow: 0 16px 48px rgba(15, 23, 42, 0.18);
      display: none; flex-direction: column; overflow: hidden;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    #mlx-support-panel.mlx-open { display: flex; }
    #mlx-support-header {
      background-image: linear-gradient(135deg, #ff6b00 0%, #f5a623 100%);
      color: #fff; padding: 14px 16px; font-weight: 600; font-size: 14px;
      display: flex; align-items: center; justify-content: space-between;
    }
    #mlx-support-close { background: none; border: none; color: #fff; font-size: 18px; cursor: pointer; padding: 0 4px; }
    #mlx-support-transcript { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 8px; background: #f8fafc; }
    .mlx-bubble { max-width: 85%; border-radius: 16px; padding: 8px 12px; font-size: 13.5px; line-height: 1.4; }
    .mlx-bubble.mlx-visitor { align-self: flex-end; border-bottom-right-radius: 4px; color: #fff; background-image: linear-gradient(135deg, #ff6b00 0%, #f5a623 100%); }
    .mlx-bubble.mlx-agent { align-self: flex-start; border-bottom-left-radius: 4px; background: #e2e8f0; color: #1e293b; }
    #mlx-support-slots { display: none; flex-direction: column; gap: 6px; padding: 0 14px 10px; }
    .mlx-slot-btn { width: 100%; text-align: left; border: 1px solid #e2e8f0; border-radius: 10px; padding: 8px 10px; font-size: 13px; background: #fff; cursor: pointer; color: #1e293b; }
    .mlx-slot-btn:hover { border-color: #f5a623; background: #fff7ed; }
    #mlx-support-form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e2e8f0; background: #fff; }
    #mlx-support-input { flex: 1; border: 1px solid #e2e8f0; border-radius: 9999px; padding: 8px 14px; font-size: 13.5px; outline: none; }
    #mlx-support-input:focus { border-color: #f5a623; }
    #mlx-support-send { border: none; border-radius: 9999px; padding: 8px 16px; color: #fff; font-size: 13.5px; font-weight: 600; cursor: pointer; background-image: linear-gradient(135deg, #ff6b00 0%, #f5a623 100%); }
    #mlx-support-send:disabled, #mlx-support-input:disabled { opacity: 0.6; cursor: not-allowed; }
  `;
  document.head.appendChild(style);

  document.body.insertAdjacentHTML(
    "beforeend",
    `
    <button id="mlx-support-bubble" aria-label="Open chat" aria-haspopup="dialog">💬</button>
    <div id="mlx-support-panel" role="dialog" aria-label="Chat with Mielikkix">
      <div id="mlx-support-header">
        <span>Chat with Mielikkix</span>
        <button id="mlx-support-close" aria-label="Close chat">✕</button>
      </div>
      <div id="mlx-support-transcript"></div>
      <div id="mlx-support-slots"></div>
      <form id="mlx-support-form">
        <input id="mlx-support-input" type="text" placeholder="Type a message..." autocomplete="off" />
        <button id="mlx-support-send" type="submit">Send</button>
      </form>
    </div>
  `
  );

  const bubble = document.getElementById("mlx-support-bubble");
  const panel = document.getElementById("mlx-support-panel");
  const closeBtn = document.getElementById("mlx-support-close");
  const transcriptEl = document.getElementById("mlx-support-transcript");
  const slotsWrap = document.getElementById("mlx-support-slots");
  const form = document.getElementById("mlx-support-form");
  const input = document.getElementById("mlx-support-input");
  const sendBtn = document.getElementById("mlx-support-send");

  let opened = false;
  function openPanel() {
    panel.classList.add("mlx-open");
    if (!opened) {
      opened = true;
      addBubble("agent", "Hi! Ask me anything about Mielikkix, or say you'd like to book a call.");
    }
  }
  bubble.addEventListener("click", () => {
    if (panel.classList.contains("mlx-open")) {
      panel.classList.remove("mlx-open");
    } else {
      openPanel();
    }
  });
  closeBtn.addEventListener("click", () => panel.classList.remove("mlx-open"));

  // Support Triage has no dedicated /demo page of its own (see agents.astro's
  // own comment on its "Talk to it now" card) -- this widget IS the demo,
  // wherever it's embedded, so a visitor arriving via ?talk-to-support=1
  // should actually see it open, not just land on a page where a bubble
  // happens to also be present somewhere in the corner.
  if (new URLSearchParams(location.search).get("talk-to-support")) {
    openPanel();
    const url = new URL(location.href);
    url.searchParams.delete("talk-to-support");
    history.replaceState({}, "", url);
  }

  function addBubble(who, text) {
    const p = document.createElement("p");
    p.className = "mlx-bubble " + (who === "visitor" ? "mlx-visitor" : "mlx-agent");
    p.textContent = text;
    transcriptEl.appendChild(p);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
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

  function formatSlot(startISO) {
    return new Date(startISO).toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  // Booking handoff state -- separate from the main chat/message loop
  // above once suggest_booking_flow fires (see support_service.py's
  // handle_chat_message, Phase 3). Reuses the same two-step
  // /api/agents/booking/request + /confirm contract booking-assistant.js
  // and the tenant widget's BookingFlow.tsx already use, with no
  // business_id -- this widget always books against Mielikkix's own demo
  // calendar (agents_voice.py and the standalone booking demo do the same;
  // see booking_service.py's _resolve_calendar_provider).
  let inBookingFlow = false;
  let bookingStage = null; // "describe" | "awaiting_slot" | "awaiting_name" | "awaiting_email"
  let meetingType = "appointment";
  let chosenSlot = null;
  let visitorName = "";

  function showSlots(slots) {
    slotsWrap.innerHTML = "";
    slotsWrap.style.display = "flex";
    for (const slot of slots) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mlx-slot-btn";
      btn.textContent = formatSlot(slot.start);
      btn.addEventListener("click", () => pickSlot(slot));
      slotsWrap.appendChild(btn);
    }
  }

  function hideSlots() {
    slotsWrap.style.display = "none";
    slotsWrap.innerHTML = "";
  }

  function pickSlot(slot) {
    chosenSlot = slot;
    hideSlots();
    addBubble("visitor", formatSlot(slot.start));
    addBubble("agent", "Great -- what's your name?");
    bookingStage = "awaiting_name";
    input.placeholder = "Your name";
  }

  async function startBookingFlow(seedMessage) {
    inBookingFlow = true;
    bookingStage = "describe";
    addBubble("agent", "Let me check what's open...");
    try {
      const result = await postJSON("/api/agents/booking/request", { message: seedMessage, timezone });
      meetingType = result.meeting_type || "appointment";
      if (result.status === "clarification_needed") {
        addBubble("agent", result.clarification_question);
        return;
      }
      if (result.status === "no_availability" || result.status === "not_configured") {
        addBubble("agent", "I couldn't find any open times right now -- I'll have someone from our team follow up instead.");
        inBookingFlow = false;
        bookingStage = null;
        return;
      }
      addBubble("agent", `Here's what's open for a ${result.duration_minutes}-minute ${meetingType}:`);
      showSlots(result.slots);
      bookingStage = "awaiting_slot";
    } catch (err) {
      console.error("Support widget booking error:", err);
      addBubble("agent", "Sorry, something went wrong checking availability. Please try again.");
      inBookingFlow = false;
      bookingStage = null;
    }
  }

  async function confirmBooking(visitorEmail) {
    addBubble("agent", "Booking that in...");
    try {
      const result = await postJSON("/api/agents/booking/confirm", {
        name: visitorName,
        email: visitorEmail,
        start: chosenSlot.start,
        end: chosenSlot.end,
        timezone,
        meeting_type: meetingType,
      });
      if (result.status === "conflict") {
        addBubble("agent", "Sorry, that time was just taken -- what would you like to book instead?");
        bookingStage = "describe";
        input.placeholder = "Type a message...";
        chosenSlot = null;
        return;
      }
      addBubble("agent", `You're booked! A calendar invite is on its way to ${visitorEmail}.`);
      inBookingFlow = false;
      bookingStage = null;
      input.placeholder = "Type a message...";
      chosenSlot = null;
      visitorName = "";
    } catch (err) {
      console.error("Support widget booking error:", err);
      addBubble("agent", "Sorry, something went wrong booking that. Please try again.");
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addBubble("visitor", text);

    input.disabled = true;
    sendBtn.disabled = true;
    try {
      if (inBookingFlow) {
        if (bookingStage === "awaiting_slot") {
          addBubble("agent", "Pick one of the times above, or type a different day to check.");
        } else if (bookingStage === "awaiting_name") {
          visitorName = text;
          addBubble("agent", "And what's the best email for the calendar invite?");
          bookingStage = "awaiting_email";
          input.placeholder = "you@example.com";
        } else if (bookingStage === "awaiting_email") {
          await confirmBooking(text);
        } else {
          await startBookingFlow(text);
        }
      } else {
        const result = await postJSON("/api/agents/support/chat/message", {
          session_id: getSessionId(),
          message: text,
        });
        addBubble("agent", result.reply);
        if (result.suggest_booking_flow) {
          await startBookingFlow(text);
        }
      }
    } catch (err) {
      console.error("Support widget error:", err);
      addBubble("agent", "Sorry, something went wrong reaching the server. Please try again.");
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });
})();
