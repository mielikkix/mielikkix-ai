# Mielikkix AI — Claude Code Project Instructions

You are working on the **Mielikkix AI** SaaS platform.

Before making any code changes, understand and follow the architecture and product principles below. Your job is not only to make the immediate feature work, but to keep the codebase scalable for a multi-tenant SaaS product.

---

## 1. Product Vision

Mielikkix is an AI-powered SaaS platform that provides businesses with different AI products and agents.

The customer-facing products may include:

- AI Chatbot
- AI Agents
- Booking Assistant
- Voice Receptionist
- Custom AI Agents

These are separate products/features from a pricing and marketing perspective, but they should share reusable infrastructure internally.

Do NOT build completely independent systems for each product when functionality can be shared.

---

# 2. Core Architecture Principle

Use this mental model:

```text
                         MIELIKKIX AI PLATFORM
                                  │
                         ┌────────┴────────┐
                         │    AI CORE      │
                         │ Agent Framework │
                         └────────┬────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
           Chatbot          Booking Assistant    Voice Receptionist
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                            Shared Tools
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
          Knowledge            Booking              Leads
             │                    │                    │
             │             ┌──────┴──────┐             │
             │             │             │             │
             │          Calendar       Booking         │
             │          Service        Database        │
             │             │             │             │
             └─────────────┴─────────────┴─────────────┘
```

The important distinction is:

**Chatbot = communication interface**

**Voice = communication interface**

**Booking Assistant = business capability / agent**

**Booking Engine = reusable backend service**

Do not confuse the UI/channel with the underlying business capability.

---

# 3. Chatbot Architecture

The website chatbot should be able to communicate with the AI Agent Core.

The AI Agent Core should determine the user's intent and decide which tools/capabilities are required.

Example:

```text
Customer:
"I want to book an appointment."

        ↓

Chatbot
        ↓

AI Agent Core
        ↓

Intent = booking
        ↓

Booking capability
        ↓

check_availability()
        ↓

Customer selects slot
        ↓

create_booking()
        ↓

Confirmation
```

The chatbot should NOT contain hardcoded booking logic.

Booking logic belongs in the backend Booking Service/Booking Agent tools.

---

# 4. Booking Assistant Architecture

The Booking Assistant should provide reusable tools/functions such as:

```text
get_services()
check_availability()
create_booking()
get_booking()
cancel_booking()
reschedule_booking()
```

For the initial MVP, prioritize:

```text
get_services()
check_availability()
create_booking()
```

Do not over-engineer cancellation and rescheduling until the core booking flow works reliably.

The Booking Assistant must NEVER invent availability.

Availability must always come from the configured calendar/booking backend.

The AI must only tell the customer that an appointment is confirmed AFTER the backend successfully creates the booking.

Correct:

```text
AI
 ↓
create_booking()
 ↓
Backend success
 ↓
AI says "Your booking is confirmed."
```

Incorrect:

```text
AI decides booking succeeded
 ↓
AI tells customer it is confirmed
```

---

# 5. Google Calendar Integration

Mielikkix has created a dedicated Google account:

**mielikkix@gmail.com**

This account will initially be used for:

- Mielikkix development
- Google Calendar integration
- Demo booking calendar
- Google Cloud/API development
- OAuth testing
- End-to-end Booking Assistant demonstration

Create/use a Google Calendar such as:

**Mielikkix Demo Bookings**

The initial live demo should use this calendar.

IMPORTANT:

Do NOT design the application as if every future customer will use `mielikkix@gmail.com`.

This account is for Mielikkix's own demo/development environment.

The eventual SaaS architecture must support:

```text
Mielikkix
    │
    ├── Demo Calendar
    │
    ├── Customer A → Google Calendar
    │
    ├── Customer B → Google Calendar
    │
    ├── Customer C → Microsoft Outlook
    │
    └── Future calendar providers
```

Use an abstraction/interface around calendar operations so the Booking Service is not tightly coupled to Google Calendar.

Example conceptual interface:

```text
CalendarProvider

- checkAvailability()
- createEvent()
- getEvent()
- updateEvent()
- deleteEvent()
```

Google Calendar should be one implementation of this interface.

Do not put Google-specific API calls throughout the application.

---

# 6. Google Calendar OAuth

For the Mielikkix demo/development environment, configure Google Calendar integration around the dedicated Mielikkix Google account.

For the future SaaS:

Customers must connect their own calendars through OAuth.

Never ask customers for:

- Google passwords
- Calendar passwords
- raw personal credentials

Use OAuth authorization.

The application should eventually store the necessary OAuth tokens securely and associate them with the correct tenant/customer.

Never expose access tokens to the frontend.

Never hardcode credentials or API secrets in source code.

Use environment variables/secrets management.

---

# 7. Multi-Tenant SaaS Architecture

Mielikkix is intended to become a multi-tenant SaaS.

Every business/customer must have isolated configuration and data.

Conceptually:

```text
Tenant
│
├── Business
│
├── Users
│
├── Knowledge Base
│
├── Agents
│
├── Chatbot configuration
│
├── Booking configuration
│
├── Calendar connections
│
├── Voice configuration
│
├── Leads
│
├── Bookings
│
└── Analytics
```

Never create global booking/customer data that could accidentally mix tenants.

Every tenant-owned resource should be associated with the correct tenant/business.

---

# 8. Business Configuration

A business should eventually have configuration such as:

```text
Business
- name
- description
- website
- address
- phone
- email
- timezone
- languages
- business hours
```

This information can be used by the AI Agent Core.

---

# 9. Booking Configuration

A tenant's booking configuration should support:

```text
Services
- name
- description
- duration
- price
- buffer time

Availability
- working days
- working hours
- breaks
- holidays
- minimum booking notice
- maximum advance booking period

Booking fields
- name
- email
- phone
- company
- custom fields
```

Do not hardcode these values.

They must be configurable per tenant.

---

# 10. Voice Receptionist Architecture

The Voice Receptionist should use the same AI Agent Core and reusable backend tools as the website chatbot.

Do NOT build separate booking logic for voice.

Correct architecture:

```text
                 Booking Service
                       ▲
                       │
             ┌─────────┴─────────┐
             │                   │
         Website Chat         Voice AI
             │                   │
             └─────────┬─────────┘
                       │
                Same booking tools
```

The Voice Receptionist may eventually support:

```text
answer_questions()
capture_lead()
check_availability()
create_booking()
cancel_booking()
reschedule_booking()
transfer_to_human()
```

The voice layer should be responsible for voice communication, not duplicating business logic.

---

# 11. Voice Integration

Mielikkix plans to use a telephony provider such as Twilio for the Voice Receptionist.

Keep telephony-specific logic isolated behind a voice/telephony layer.

Do not spread Twilio-specific code throughout unrelated business logic.

Conceptually:

```text
Incoming Call
      ↓
Telephony Provider
      ↓
Mielikkix Voice Layer
      ↓
AI Agent Core
      ↓
Shared Tools
      ↓
Booking / Lead / Knowledge systems
```

The Voice Receptionist and website chatbot should ultimately be able to use the same underlying business tools.

---

# 12. Knowledge Base

AI Agents should have access to business-specific knowledge.

Possible sources:

```text
Website
PDF documents
FAQs
Manual business information
Policies
Product/service information
```

Knowledge must be tenant-specific.

Do not allow one customer's knowledge to become available to another customer's AI.

---

# 13. Product and Pricing Separation

Mielikkix may sell the following as separate products/plans:

```text
AI Chatbot
AI Agent
Booking Assistant
Voice Receptionist
Custom AI Agent
```

Do not assume that every customer gets every capability.

Features should be controlled through configuration/plan entitlements.

For example:

```text
Basic Chatbot
    └── chatbot enabled
    └── booking disabled

Booking Assistant
    └── chatbot enabled
    └── booking enabled

Voice Receptionist
    └── voice enabled
    └── booking optional

Premium Agent
    └── selected tools enabled
```

However, internally, reusable services should be shared.

---

# 14. Live Demo Goal

The immediate product goal is to create a fully working **Mielikkix Booking Assistant live preview** on the promotion website.

The target end-to-end flow is:

```text
Mielikkix Promotion Website
          ↓
AI Chatbot
          ↓
Customer:
"I want to book a consultation."
          ↓
AI Agent Core
          ↓
Booking intent detected
          ↓
Booking Assistant
          ↓
get_services()
          ↓
check_availability()
          ↓
Google Calendar
(Mielikkix demo account)
          ↓
Available slots returned
          ↓
Customer selects slot
          ↓
Collect customer information
          ↓
create_booking()
          ↓
Google Calendar event created
          ↓
Booking stored in Mielikkix database
          ↓
Confirmation
```

This must be a REAL end-to-end demo, not a simulated chatbot response.

---

# 15. Demo Environment

The Mielikkix demo should initially use:

```text
Google Account:
mielikkix@gmail.com

Calendar:
Mielikkix Demo Bookings
```

The demo should have predefined business information, services and availability.

The visitor should be able to experience:

```text
Conversation
     ↓
Service selection
     ↓
Availability
     ↓
Time selection
     ↓
Customer details
     ↓
Confirmation
     ↓
Real calendar event
```

The goal is to make the visitor believe they are interacting with a real AI employee because the entire workflow actually works.

---

# 16. Confirmation and Email

After successful booking:

```text
Booking created
       ↓
Confirmation generated
       ↓
Customer receives confirmation
       ↓
Business receives notification
```

The existing Mielikkix business email is:

**post@mielikkix.no**

This mailbox is hosted through Domene.shop.

Do NOT assume that because Google Calendar is being used, the business email must also be moved to Google.

Email and calendar are separate services.

Current conceptual setup:

```text
post@mielikkix.no
    ↓
Business email
Domene.shop

mielikkix@gmail.com
    ↓
Google Calendar
Google APIs
Demo environment
```

Keep this separation.

---

# 17. Security Rules

Never:

- Hardcode API keys
- Hardcode OAuth secrets
- Commit `.env` files
- Store Google access tokens in frontend code
- Trust booking confirmation generated by the LLM
- Allow cross-tenant data access
- Put provider-specific business logic everywhere

Always:

- Use environment variables
- Validate backend input
- Validate authorization
- Validate tenant ownership
- Keep secrets server-side
- Verify booking creation succeeded
- Log important booking failures
- Handle calendar API failures gracefully

---

# 18. Coding Principles

Before implementing a feature:

1. Inspect the existing repository.
2. Understand the existing architecture.
3. Reuse existing services/components where appropriate.
4. Do not create duplicate implementations.
5. Prefer modular services.
6. Keep provider integrations isolated.
7. Keep tenant-specific data isolated.
8. Keep frontend and backend responsibilities clear.
9. Do not make unnecessary breaking changes.
10. Preserve existing working functionality.

When a new feature can be implemented as a reusable service, prefer that over putting business logic directly inside a UI component.

---

# 19. Before Making Major Changes

For significant architectural changes:

1. Explain the current architecture you discovered.
2. Identify which existing components can be reused.
3. Identify what needs to be added.
4. Explain any database/API changes.
5. Explain how the change supports future SaaS multi-tenancy.
6. Then implement.

Do not rewrite the project unnecessarily.

---

# 20. Priority Roadmap

The current development priority is:

### Phase 1 — Booking MVP

```text
Booking data model
        ↓
Services
        ↓
Availability
        ↓
Google Calendar integration
        ↓
check_availability()
        ↓
create_booking()
        ↓
Booking confirmation
```

### Phase 2 — Website Chat

```text
Mielikkix Chatbot
        ↓
AI Agent Core
        ↓
Booking tools
```

### Phase 3 — Live Demo

```text
Mielikkix promotion site
        ↓
Live Booking Assistant
        ↓
Real Google Calendar booking
        ↓
Confirmation
```

### Phase 4 — Voice

```text
Twilio
   ↓
Voice Receptionist
   ↓
AI Agent Core
   ↓
Same Booking tools
```

### Phase 5 — SaaS

```text
Customer onboarding
        ↓
Business configuration
        ↓
Knowledge base
        ↓
Calendar OAuth
        ↓
Agent configuration
        ↓
Voice configuration
        ↓
Multi-tenant dashboard
```

---

# 21. Most Important Architectural Rule

Always remember:

> **One shared AI/agent infrastructure, multiple customer-facing products and channels.**

The website chatbot, Booking Assistant and Voice Receptionist should not become three completely separate systems.

Instead:

```text
                     MIELIKKIX AI CORE
                            │
                    ┌───────┴───────┐
                    │               │
                 Channels          Tools
                    │               │
             ┌──────┼──────┐       ├── Knowledge
             │      │      │       ├── Booking
           Chat   Voice   Future    ├── Leads
                            │       ├── Calendar
                            │       └── CRM
                            │
                         Customers
```

Build reusable infrastructure now so Mielikkix can scale from a demo into a real SaaS platform without a major rewrite.

---

# 22. Your First Task

Before modifying the application:

**Inspect the entire existing `mielikkix-ai` repository and understand:**

- Frontend architecture
- Backend architecture
- Existing AI/agent implementation
- Existing chatbot implementation
- Existing database models
- Existing authentication
- Existing API structure
- Existing environment configuration
- Existing dashboard
- Existing deployment architecture
- Existing integrations

Then report:

1. What already exists
2. What can be reused
3. What is missing for Booking Assistant
4. What is missing for Google Calendar
5. What database changes are required
6. What APIs/tools need to be added
7. Recommended implementation order

Do NOT start a large rewrite.

The immediate objective is to add the **Booking Assistant capability and Google Calendar demo integration cleanly into the existing Mielikkix architecture** while preserving all existing functionality.