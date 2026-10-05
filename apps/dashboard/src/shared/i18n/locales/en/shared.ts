// Reusable dashboard components (English).

export const gates = {
  higherPlan: 'Available on a higher plan.',
  comingSoon: 'Coming soon.',
  upgrade: 'Upgrade',
  agentInactive: 'Not active on your account yet.',
  contactUs: 'Contact us',
}

export const usage = {
  unlimitedOnPlan: '(unlimited on your plan)',
  upgradeForMore: 'Upgrade for more',
}

export const currency = {
  label: 'Currency',
  names: { EUR: 'Euro', USD: 'US Dollar', NOK: 'Norwegian Krone' },
}

export const payment = {
  soonTitle: 'Payment integration coming soon',
  soonBefore: "We're not able to process card payments yet, so upgrading to the ",
  soonAfter: " plan isn't available right now. We're working on it and will let you know as soon as it's ready.",
  gotIt: 'Got it',
}

export const checkout = {
  title: 'Upgrade to {plan}',
  planLine: '{plan} plan',
  priceExclVat: '{price}/mo excl. VAT',
  approx: '≈ {price}/mo',
  cardName: 'Name on card',
  cardNamePlaceholder: 'Jane Doe',
  cardNumber: 'Card number',
  expiry: 'Expiry',
  expiryPlaceholder: 'MM/YY',
  cvc: 'CVC',
  errCardName: 'Enter the name on the card',
  errCardDigits: 'Card number must be 16 digits',
  errCardCheck: "That card number doesn't look right",
  errExpiryFormat: 'Enter expiry as MM/YY',
  errExpiryMonth: 'Enter a valid month',
  errExpired: 'Card has expired',
  errCvc: 'Enter a valid CVC',
  demoNotice:
    'No payment processor is connected yet, so no real charge is made and card details are never sent or stored anywhere. This switches your plan for demo purposes only.',
  failed: "Couldn't complete the upgrade. Please try again.",
  pay: 'Pay {price}/mo and upgrade',
}

export const knowledge = {
  title: { one: '{count} possible contradiction in your chatbot\'s knowledge', other: "{count} possible contradictions in your chatbot's knowledge" },
  similarFaqs: 'These FAQs ask nearly the same question but give different answers. The chatbot may pick either one.',
  priceMismatch: 'This product is listed more than once with different prices. The chatbot may quote either one.',
  noPrice: 'no price',
}

export const testChat = {
  title: 'Test your chatbot',
  intro:
    "Ask what your customers ask and check the answers. Test chats don't count toward your plan and aren't saved in Conversations.",
  examples: 'Try: "What are your opening hours?" or "How much does it cost?"',
  weak: "Your knowledge base doesn't seem to cover this. Add an FAQ or a document so the chatbot can answer it.",
  thinking: 'Thinking…',
  failed: "Couldn't get an answer. Please try again.",
  placeholder: 'Type a question…',
  inputLabel: 'Test question',
  send: 'Send test question',
  reset: 'Start over',
}
