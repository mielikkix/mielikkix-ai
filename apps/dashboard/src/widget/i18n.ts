// Static UI chrome for the widget (lead form, placeholders, error/status
// messages) -- separate from the AI-generated reply/welcome-message text,
// which is translated server-side instead. Extend as more languages get
// real coverage; anything missing here falls back to English.

export interface WidgetStrings {
  leadFormIntro: string
  namePlaceholder: string
  emailPlaceholder: string
  phonePlaceholder: string
  messagePlaceholder: string
  send: string
  sending: string
  leadInvalidError: string
  leadGenericError: string
  leadThanks: string
  rateLimited: string
  chatError: string
  inputPlaceholder: string
  openChat: string
  closeChat: string
  bookingFindTimes: string
  bookingFinding: string
  bookingNoAvailability: string
  bookingNamePlaceholder: string
  bookingEmailPlaceholder: string
  bookingConfirm: string
  bookingConfirming: string
  bookingConflict: string
  bookingGenericError: string
  bookingBackToDescribe: string
  bookingBackToSlots: string
  bookingBooked: string
}

const EN: WidgetStrings = {
  leadFormIntro: "Leave your contact details and we'll get back to you:",
  namePlaceholder: 'Your name *',
  emailPlaceholder: 'Email',
  phonePlaceholder: 'Phone',
  messagePlaceholder: 'Message (optional)',
  send: 'Send',
  sending: 'Sending…',
  leadInvalidError: 'Please check your email and phone number are valid.',
  leadGenericError: 'Something went wrong. Please try again.',
  leadThanks: "Thanks! We'll be in touch soon.",
  rateLimited: "You're sending messages a bit too fast — please wait a moment and try again.",
  chatError: 'Sorry, something went wrong. Please try again.',
  inputPlaceholder: 'Type a message…',
  openChat: 'Open chat',
  closeChat: 'Close chat',
  bookingFindTimes: 'Find times',
  bookingFinding: 'Finding times…',
  bookingNoAvailability: 'No open times in that window — try a different day or date range.',
  bookingNamePlaceholder: 'Your name',
  bookingEmailPlaceholder: 'Your email',
  bookingConfirm: 'Confirm booking',
  bookingConfirming: 'Booking…',
  bookingConflict: 'Sorry, that time was just taken. Please pick another.',
  bookingGenericError: 'Sorry, something went wrong. Please try again.',
  bookingBackToDescribe: '← Describe something else',
  bookingBackToSlots: '← Pick a different time',
  bookingBooked: "You're booked!",
}

const WIDGET_STRINGS: Record<string, WidgetStrings> = {
  en: EN,
  no: {
    leadFormIntro: 'Legg igjen kontaktinformasjonen din, så tar vi kontakt:',
    namePlaceholder: 'Navnet ditt *',
    emailPlaceholder: 'E-post',
    phonePlaceholder: 'Telefon',
    messagePlaceholder: 'Melding (valgfritt)',
    send: 'Send',
    sending: 'Sender…',
    leadInvalidError: 'Sjekk at e-post og telefonnummer er gyldige.',
    leadGenericError: 'Noe gikk galt. Vennligst prøv igjen.',
    leadThanks: 'Takk! Vi tar kontakt med deg snart.',
    rateLimited: 'Du sender meldinger litt for raskt — vent et øyeblikk og prøv igjen.',
    chatError: 'Beklager, noe gikk galt. Vennligst prøv igjen.',
    inputPlaceholder: 'Skriv en melding…',
    openChat: 'Åpne chat',
    closeChat: 'Lukk chat',
    bookingFindTimes: 'Finn tider',
    bookingFinding: 'Finner tider…',
    bookingNoAvailability: 'Ingen ledige tider i den perioden — prøv en annen dag eller periode.',
    bookingNamePlaceholder: 'Navnet ditt',
    bookingEmailPlaceholder: 'E-post',
    bookingConfirm: 'Bekreft booking',
    bookingConfirming: 'Booker…',
    bookingConflict: 'Beklager, den tiden ble nettopp tatt. Velg en annen.',
    bookingGenericError: 'Beklager, noe gikk galt. Vennligst prøv igjen.',
    bookingBackToDescribe: '← Beskriv noe annet',
    bookingBackToSlots: '← Velg et annet tidspunkt',
    bookingBooked: 'Du er booket!',
  },
}

export function widgetStrings(lang?: string | null): WidgetStrings {
  return (lang && WIDGET_STRINGS[lang]) || EN
}
