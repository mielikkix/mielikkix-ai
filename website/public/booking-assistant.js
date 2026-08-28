// The /demo/booking-assistant page's step-through logic. External file
// (not an inline <script>) for the same Content-Security-Policy reason
// voice-receptionist.js is -- see that file's own comment on this.
const { apiUrl } = document.currentScript.dataset;

const stepDescribe = document.getElementById("step-describe");
const stepSlots = document.getElementById("step-slots");
const stepDetails = document.getElementById("step-details");
const stepDone = document.getElementById("step-done");

const requestInput = document.getElementById("requestInput");
const findTimesBtn = document.getElementById("findTimesBtn");
const describeError = document.getElementById("describeError");

const slotsIntro = document.getElementById("slotsIntro");
const slotsList = document.getElementById("slotsList");
const backToDescribeBtn = document.getElementById("backToDescribeBtn");

const chosenSlotLabel = document.getElementById("chosenSlotLabel");
const nameInput = document.getElementById("nameInput");
const emailInput = document.getElementById("emailInput");
const confirmBtn = document.getElementById("confirmBtn");
const detailsError = document.getElementById("detailsError");
const backToSlotsBtn = document.getElementById("backToSlotsBtn");

const doneDetail = document.getElementById("doneDetail");
const bookAnotherBtn = document.getElementById("bookAnotherBtn");

// The browser already knows the visitor's real timezone precisely --
// sent straight to the server rather than asked of the LLM (see
// agents_booking.py's _RequestBookingBody comment on why parsing a
// timezone out of free text is a bad idea).
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

let chosenSlot = null; // { start, end } ISO strings, exactly as offered
let meetingType = "appointment";

function showStep(step) {
  for (const el of [stepDescribe, stepSlots, stepDetails, stepDone]) {
    el.classList.toggle("hidden", el !== step);
  }
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
  const start = new Date(startISO);
  return start.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function renderSlots(slots) {
  slotsList.innerHTML = "";
  for (const slot of slots) {
    const btn = document.createElement("button");
    btn.className =
      "w-full rounded-2xl border border-slate-200 p-3 text-left text-sm font-medium text-slate-700 transition-colors hover:border-violet-400 hover:bg-violet-50";
    btn.textContent = formatSlot(slot.start);
    btn.addEventListener("click", () => {
      chosenSlot = slot;
      chosenSlotLabel.textContent = formatSlot(slot.start);
      detailsError.classList.add("hidden");
      showStep(stepDetails);
    });
    slotsList.appendChild(btn);
  }
}

async function findTimes() {
  const message = requestInput.value.trim();
  describeError.classList.add("hidden");
  if (!message) {
    describeError.textContent = "Tell us what you'd like to book first.";
    describeError.classList.remove("hidden");
    return;
  }

  findTimesBtn.disabled = true;
  findTimesBtn.textContent = "Finding times...";
  try {
    const result = await postJSON("/api/agents/booking/dev/request", { message, timezone });
    meetingType = result.meeting_type || "appointment";

    if (result.status === "clarification_needed") {
      describeError.textContent = result.clarification_question;
      describeError.classList.remove("hidden");
      return;
    }
    if (result.status === "no_availability") {
      describeError.textContent = "No open times in that window -- try a different day or date range.";
      describeError.classList.remove("hidden");
      return;
    }

    slotsIntro.textContent = `Here's what's open for a ${result.duration_minutes}-minute ${meetingType}:`;
    renderSlots(result.slots);
    showStep(stepSlots);
  } catch (err) {
    console.error("Failed to find times:", err);
    describeError.textContent = "Sorry, something went wrong reaching the server. Please try again.";
    describeError.classList.remove("hidden");
  } finally {
    findTimesBtn.disabled = false;
    findTimesBtn.textContent = "Find times";
  }
}

async function confirmBooking() {
  const name = nameInput.value.trim();
  const email = emailInput.value.trim();
  detailsError.classList.add("hidden");
  if (!name || !email) {
    detailsError.textContent = "Please enter your name and email.";
    detailsError.classList.remove("hidden");
    return;
  }

  confirmBtn.disabled = true;
  confirmBtn.textContent = "Booking...";
  try {
    const result = await postJSON("/api/agents/booking/dev/confirm", {
      name,
      email,
      start: chosenSlot.start,
      end: chosenSlot.end,
      timezone,
      meeting_type: meetingType,
    });

    if (result.status === "conflict") {
      detailsError.textContent = "Sorry, that time was just taken. Please pick another.";
      detailsError.classList.remove("hidden");
      showStep(stepSlots);
      return;
    }

    doneDetail.textContent = `${formatSlot(chosenSlot.start)} -- a calendar invite is on its way to ${email}.`;
    showStep(stepDone);
  } catch (err) {
    console.error("Failed to confirm booking:", err);
    detailsError.textContent = "Sorry, something went wrong reaching the server. Please try again.";
    detailsError.classList.remove("hidden");
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Confirm booking";
  }
}

function resetToStart() {
  requestInput.value = "";
  nameInput.value = "";
  emailInput.value = "";
  chosenSlot = null;
  showStep(stepDescribe);
}

findTimesBtn.addEventListener("click", findTimes);
backToDescribeBtn.addEventListener("click", () => showStep(stepDescribe));
backToSlotsBtn.addEventListener("click", () => showStep(stepSlots));
confirmBtn.addEventListener("click", confirmBooking);
bookAnotherBtn.addEventListener("click", resetToStart);
