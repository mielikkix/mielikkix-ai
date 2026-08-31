"""Regression coverage for a bug found during manual dashboard testing
(2026-08-30): the "Add FAQ" and "Add product" forms had no validation
anywhere -- clicking Save with empty/whitespace-only required fields
silently created a blank record, with no error shown in the UI or logged
server-side. Fixed at the schema layer (the one place every request, from
any client, has to pass through) via a shared "reject blank after
stripping" validator on FAQCreate/FAQUpdate.question+answer and
ProductCreate/ProductUpdate.name -- these tests pin that behavior so it
can't silently regress.
"""

import pytest
from pydantic import ValidationError

from app.schemas.faq import FAQCreate, FAQUpdate
from app.schemas.product import ProductCreate, ProductUpdate


@pytest.mark.parametrize("bad_value", ["", "   ", "\t\n"])
def test_faq_create_rejects_blank_question(bad_value):
    with pytest.raises(ValidationError):
        FAQCreate(question=bad_value, answer="A real answer")


@pytest.mark.parametrize("bad_value", ["", "   "])
def test_faq_create_rejects_blank_answer(bad_value):
    with pytest.raises(ValidationError):
        FAQCreate(question="A real question", answer=bad_value)


def test_faq_create_strips_and_accepts_real_content():
    faq = FAQCreate(question="  What are your hours?  ", answer="  9 to 5.  ", category=None)
    assert faq.question == "What are your hours?"
    assert faq.answer == "9 to 5."


def test_faq_update_rejects_blank_but_allows_omitted_field():
    with pytest.raises(ValidationError):
        FAQUpdate(question="   ")
    # Omitting a field entirely (not editing it) must stay allowed --
    # only an explicit blank value is rejected.
    update = FAQUpdate(answer="Updated answer")
    assert update.question is None
    assert update.answer == "Updated answer"


@pytest.mark.parametrize("bad_value", ["", "   "])
def test_product_create_rejects_blank_name(bad_value):
    with pytest.raises(ValidationError):
        ProductCreate(name=bad_value)


def test_product_create_strips_and_accepts_real_name():
    product = ProductCreate(name="  Consulting Call  ")
    assert product.name == "Consulting Call"


def test_product_update_rejects_blank_but_allows_omitted_field():
    with pytest.raises(ValidationError):
        ProductUpdate(name="   ")
    update = ProductUpdate(description="New description")
    assert update.name is None
