"""Intent detection drives lead-capture: chat_service sets
suggest_lead_capture when the intent is "lead" (or confidence is low), and the
widget then shows the contact form. Substring matching used to misfire on
ordinary words containing a keyword, which popped that form on questions that
had nothing to do with getting in touch -- these lock in whole-word matching.

Also covers "booking" (added alongside Booking Assistant's chat-widget
handoff, see chat_service.py's suggest_booking_flow) -- checked before
"lead" so a real booking request isn't swallowed by lead's broader
"schedule"/"demo"/"call" keywords.
"""

import pytest

from app.rag.pipeline import _detect_intent


@pytest.mark.parametrize(
    "message",
    [
        "How can I contact you?",
        "Can someone call me back?",
        "What's your email?",
        "How do I reach the owner?",
        "Do you have a phone number?",
    ],
)
def test_contact_questions_are_leads(message):
    assert _detect_intent(message) == "lead"


@pytest.mark.parametrize(
    "message,expected",
    [
        # "locally" contains "call", "headphones" contains "phone" -- neither is
        # someone asking to be contacted, so neither should show the lead form.
        ("Are your ingredients sourced locally?", "faq"),
        ("Do you sell headphones?", "faq"),
        # "coffee" contains "fee" -- for a cafe this mislabelled nearly every
        # question as a pricing question.
        ("Is the coffee good?", "faq"),
        ("Do you have vegan options?", "faq"),
    ],
)
def test_words_merely_containing_a_keyword_are_not_matched(message, expected):
    assert _detect_intent(message) == expected


@pytest.mark.parametrize(
    "message",
    ["What is the price?", "How much is a latte?", "Is there a delivery fee?"],
)
def test_pricing_questions_are_product_inquiries(message):
    assert _detect_intent(message) == "product_inquiry"


def test_support_questions():
    assert _detect_intent("The order page is not working") == "support"


def test_plain_question_defaults_to_faq():
    assert _detect_intent("What are your opening hours?") == "faq"


@pytest.mark.parametrize(
    "message",
    [
        "I want to book a consultation",
        "Can I book an appointment for next week?",
        "I need to reschedule my appointment",
    ],
)
def test_booking_requests_are_booking(message):
    assert _detect_intent(message) == "booking"


def test_generic_scheduling_language_without_book_stays_a_lead():
    """Deliberately unchanged from before "booking" existed -- "schedule a
    demo call" has no "book"/"appointment"/"reschedule" in it, so it keeps
    classifying as a lead rather than routing into Booking Assistant's real
    availability flow for a request that isn't actually asking to book
    something specific yet."""
    assert _detect_intent("Can we schedule a demo call?") == "lead"
