// Overview (the dashboard home page) — English.

export const overview = {
  fallbackTitle: 'Dashboard',
  welcome: "Welcome back! Here's your chatbot at a glance.",
  stats: {
    conversations: 'Conversations',
    leads: 'Leads captured',
    messages: 'Visitor messages',
  },
  usageLabel: 'AI conversations this month ({plan} plan)',
  planLink: 'Plan & usage',
  topQuestions: 'Top visitor questions',
  topQuestionsLocked: 'Question breakdowns are available on the Basic plan and up.',
  upgrade: 'Upgrade',
  chats: { one: '{count} chat', other: '{count} chats' },
  byIntent: 'Conversations by intent',
  intentConversations: { one: 'conversation', other: 'conversations' },
  intents: {
    faq: 'Questions',
    lead: 'Contact requests',
    booking: 'Bookings',
    product_inquiry: 'Product & price questions',
    support: 'Support',
  },
  embed: {
    title: 'Embed your chatbot',
    introBefore: 'Copy this snippet and paste it before ',
    introAfter: ' on your website.',
    copy: 'Copy to clipboard',
    privacyTitle: 'Privacy notes for your website',
    cookiesBefore: 'The widget sets no cookies. Once a visitor opens the chat, it stores a session ID (',
    cookiesMiddle: ') and the conversation so far (',
    cookiesAfter:
      ', so it follows them from page to page) in sessionStorage, which is cleared when the tab closes. List them in your cookie and privacy notices.',
    aiNotice: "Visitors are told they're chatting with an AI assistant, with a link to your privacy policy.",
    settingsBefore: 'Set your privacy policy link and how long conversations are kept under ',
    settingsLink: 'Settings → Advanced',
    settingsAfter: '.',
  },
}
