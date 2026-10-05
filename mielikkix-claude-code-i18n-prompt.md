# Claude Code Implementation Prompt — Mielikkix Dashboard English + Norwegian (Bokmål)

## Objective

Implement proper internationalization (i18n) in the existing Mielikkix application at:

https://app.mielikkix.ai/

The application must support:

- English (`en`)
- Norwegian Bokmål (`nb`)

English must remain fully supported and should remain the default fallback.

This is a production feature. Do not create a superficial language toggle that only translates a few labels. Build a maintainable i18n architecture that can be extended later.

---

## Important business context

Mielikkix is an AI software company selling its chatbot/widget and related automation products to Norwegian small businesses.

The initial commercial market is Norway.

The goal is NOT to make the entire application Norwegian-only.

The goal is:

> One application, two supported UI languages: English and Norwegian Bokmål.

The customer's language should be selectable and should persist across sessions.

The chatbot/widget itself is a separate concern from the dashboard. This task is primarily about the authenticated Mielikkix application UI, but inspect the existing codebase and identify any existing language infrastructure that can be safely reused.

---

## Research / product rationale

Norwegian is not generally legally mandatory for a private company selling B2B software in Norway.

Språkrådet states that the Language Act does not apply to private companies and that private companies may communicate with Norwegian customers in English.

However, Språkrådet and NHO recommend using Norwegian when addressing Norwegian customers, and a 2026 Språkrådet survey reports that 99% of Norwegian businesses use Norwegian and that Norwegian remains the common language of Norwegian business.

Therefore Mielikkix should support Norwegian as a commercial/localization feature, not because a Norwegian-language dashboard is generally legally mandatory.

Public-sector customers are different. Norwegian public-sector digital solutions can have requirements for Bokmål and Nynorsk. Mielikkix is initially targeting private Norwegian SMBs, so implement `nb` (Bokmål) now. Do NOT add Nynorsk in this task unless the existing architecture makes it trivial and safe.

Privacy information is a separate concern. Norwegian data-protection guidance emphasizes that privacy information must be clear, understandable and accessible. This task must therefore avoid accidentally translating or changing legal/privacy text without explicit source content.

---

## Sources considered

Use these sources only as background/context; do not hard-code legal claims into the product:

- Språkrådet — Språkvett for næringslivet:
  https://sprakradet.no/fagsprak-terminologi-og-begrepsarbeid/sprakplakaten-sprakvett-for-naeringslivet/
- Språkrådet — Norsk er fremdeles hovedspråk i næringslivet:
  https://sprakradet.no/aktuelt/norsk-er-fremdeles-hovedsprak-i-naeringslivet/
- Språkrådet — English and private companies:
  https://sprakradet.no/spraklova/sporsmal-og-svar/sporsmal-og-svar-engelsk/
- Språkrådet — public-sector digital language requirements:
  https://sprakradet.no/sprakteknologi/krav-til-sprak-i-digitale-loysingar/sprakkrav-til-digitale-loysingar-i-offentleg-sektor/
- Datatilsynet — information and transparency:
  https://www.datatilsynet.no/rettigheter-og-plikter/virksomhetenes-plikter/informasjon-og-apenhet/

---

# STEP 1 — Inspect before changing anything

Before modifying code:

1. Identify the frontend framework.
2. Identify the build system.
3. Identify routing.
4. Identify whether SSR/SSG/client-side rendering is used.
5. Identify authentication/session management.
6. Identify the existing user/account model.
7. Identify the existing dashboard layout/navigation.
8. Identify any existing localization/i18n library or translation files.
9. Identify how user preferences are currently stored.
10. Identify whether the marketing site already has language support that can be reused.
11. Identify all authenticated dashboard routes/screens.
12. Identify email/template localization infrastructure if it exists.
13. Identify existing automated tests and testing framework.
14. Identify TypeScript strictness and linting conventions.

Do not assume React, Next.js, Angular, Astro, Vue, or any other framework.

Use the project's existing architecture and dependencies where practical.

Do NOT introduce a new i18n framework if the project already has an appropriate one.

If no i18n system exists, choose the smallest robust solution appropriate for the actual stack.

---

# STEP 2 — Produce a short implementation plan

Before making edits, provide:

- detected stack
- existing i18n situation
- proposed architecture
- files likely to change
- how locale will be persisted
- how fallback will work
- how tests will cover the feature

Then implement the plan.

Do not stop after only giving the plan.

---

# STEP 3 — Required language architecture

Implement these locales:

```text
en
nb
```

Use Norwegian Bokmål, not Nynorsk.

Recommended terminology:

- English = English
- Norwegian = Norsk

Do not expose technical locale names such as `nb` to normal users.

The language selector should be simple and obvious.

Example:

```text
English
Norsk
```

or an appropriate compact UI representation consistent with the existing design system.

Avoid flags as the primary language indicator because language is not the same thing as nationality.

---

# STEP 4 — Locale persistence

The selected language must persist.

First inspect whether the authenticated user has a preferences/settings mechanism.

Preferred order:

1. Persist the preference to the authenticated user's profile/settings if the existing backend supports user preferences.
2. Also use a client-side/browser fallback where appropriate for unauthenticated screens.
3. Never store sensitive user information in an unsafe way merely to implement language selection.

After logout/login, the authenticated user's saved preference should be restored.

If the application currently has no user-preference persistence mechanism, implement the smallest safe mechanism consistent with the existing architecture.

Do not create a new database table unless it is genuinely necessary.

---

# STEP 5 — Locale selection and fallback

Implement deterministic behavior.

Suggested behavior:

1. Explicitly saved user preference wins.
2. If no saved preference exists, use existing application/default locale behavior.
3. English is the final fallback.

Never render raw translation keys such as:

```text
dashboard.title
common.save
leads.empty
```

to users.

If a Norwegian translation is accidentally missing, fall back gracefully to English.

Add development/test protection for missing translation keys.

---

# STEP 6 — Translate the authenticated dashboard

Translate ALL user-facing dashboard UI, not just the sidebar.

At minimum inspect and cover:

## Authentication

- Login
- Register / Sign up
- Forgot password
- Reset password
- Email verification
- Authentication errors
- Session-related messages

## Navigation

- Dashboard
- Overview
- Chatbot
- Conversations
- Leads
- FAQs
- Documents / Knowledge
- Analytics
- Products, if present
- Settings
- Billing
- Support
- Logout
- Help

Use the actual screens found in the repository rather than assuming these routes exist.

## Dashboard content

Translate:

- Page titles
- Descriptions
- Buttons
- Form labels
- Placeholders
- Empty states
- Loading states
- Error states
- Success messages
- Confirmation dialogs
- Tooltips
- Dropdown labels
- Tabs
- Tables
- Pagination
- Filters
- Search UI
- Status labels
- Validation messages
- Toast notifications
- Modals
- Confirmation text

## Chatbot configuration

Translate all user-facing configuration UI that exists, including:

- General settings
- Appearance
- Behavior
- Welcome message configuration UI
- FAQ management
- Knowledge/document management
- Lead capture configuration
- Embed instructions
- Installation instructions
- Save/update/reset actions

## Leads

Translate:

- Lead list
- Lead details
- Lead statuses
- Filters
- Empty states
- Export UI
- Search UI
- Form labels

Do NOT automatically translate customer-provided lead data, business names, FAQ content, document content, or other user-generated content.

Those are data, not UI translations.

## Analytics

Translate:

- Metric names
- Chart labels
- Filters
- Date-range controls
- Empty states
- Explanations
- Tooltips

Be careful with date, number, and currency formatting.

---

# STEP 7 — Dates, numbers and currency

Do not simply translate labels.

Use proper locale-aware formatting where appropriate.

For Norwegian Bokmål:

- Use Norwegian date conventions.
- Use Norwegian number formatting.
- Preserve NOK as the business currency where the product already uses NOK.
- Do not change actual stored numeric values merely because the display locale changes.

Use the framework's or browser's standard internationalization APIs where appropriate, such as `Intl.DateTimeFormat` and `Intl.NumberFormat`.

Do not hard-code formatting strings throughout components.

---

# STEP 8 — Translation architecture

Do NOT do this:

```tsx
{locale === "nb" ? "Leads" : "Leads"}
```

Do NOT scatter language conditionals throughout components.

Prefer a centralized translation system, for example:

```ts
t("navigation.leads")
t("common.save")
t("leads.empty")
```

with translation resources such as:

```text
locales/
  en/
    ...
  nb/
    ...
```

Use the actual project conventions if an existing system is already present.

Organize translation keys logically, for example:

```text
common.*
navigation.*
auth.*
dashboard.*
chatbot.*
leads.*
faqs.*
documents.*
analytics.*
settings.*
billing.*
errors.*
validation.*
notifications.*
```

Avoid overly generic keys where they create ambiguity.

---

# STEP 9 — Do not translate dynamic content incorrectly

Translation applies to application UI.

Do NOT automatically translate:

- Business names
- Customer names
- Lead messages
- FAQ answers entered by the business
- Uploaded documents
- Product names
- Domain names
- URLs
- API responses
- User-generated chatbot knowledge
- Customer messages
- Database values

Only translate the surrounding UI unless the product explicitly has a separate content-translation feature.

---

# STEP 10 — Email and notification audit

Inspect whether Mielikkix sends emails or system notifications.

If the codebase has email templates and the language can be determined safely from the user/account preference, prepare the architecture for:

```text
en
nb
```

Prioritize customer-facing emails such as:

- New lead notifications
- Usage warnings
- Account notifications
- Password/authentication emails
- Billing notifications

Do not rewrite legal or transactional content merely for the sake of this feature.

If email localization is too large for this task, document exactly what remains and create a clean extension point.

---

# STEP 11 — Signup / login priority

The signup/login experience is commercially important because this is the first product interaction for a Norwegian customer.

Make sure:

- Signup can be displayed in Norwegian.
- Login can be displayed in Norwegian.
- Validation messages are localized.
- Error messages are localized.
- Language selection is available before authentication if practical.
- The selected language can survive signup/login.
- After login, the dashboard respects the chosen language.

Do not create a separate Norwegian application.

---

# STEP 12 — Language selector UX

Add a language selector in an appropriate existing location.

Preferred placement:

- Header/profile menu
- Settings
- Or both if consistent with the existing UX

Do not add a visually heavy control.

When a user changes language:

- UI should update without requiring a full logout.
- Current route/page should remain intact.
- Current form state should not unexpectedly disappear.
- Modals/dropdowns should remain stable where possible.
- The selected language should persist.

If SSR is used, avoid hydration mismatches caused by locale detection.

---

# STEP 13 — Accessibility

The language selector must be accessible.

Requirements:

- Keyboard accessible
- Proper button/select semantics
- Visible focus state
- Screen-reader-friendly label
- No color-only language indication
- Correct `lang` attribute on the document/root where the architecture allows it

For example:

```html
<html lang="nb">
```

when Norwegian is selected.

Use the project's existing accessibility conventions.

---

# STEP 14 — Translation quality

Norwegian translations must be natural Bokmål, not word-for-word machine-translated English.

Prefer concise SaaS/product terminology used by Norwegian businesses.

Examples:

```text
Dashboard -> Oversikt
Leads -> Leads
Settings -> Innstillinger
Save -> Lagre
Cancel -> Avbryt
Delete -> Slett
Edit -> Rediger
Search -> Søk
Documents -> Dokumenter
FAQs -> Vanlige spørsmål
Conversations -> Samtaler
Analytics -> Analyse
Billing -> Fakturering
Logout -> Logg ut
```

Important:

Some technical terms may naturally remain in English if that is normal Norwegian software terminology.

Do not translate brand names, product names, API names, programming terms, URLs, or technical identifiers unnecessarily.

Review the final Norwegian terminology for consistency.

---

# STEP 15 — Privacy / legal content

Do not make unsupported legal claims.

Do not automatically translate existing:

- Privacy Policy
- Terms of Service
- Data Processing Agreement
- Cookie policy

unless the actual source text is intentionally provided and approved for translation.

However, identify these locations in the application and report whether they are currently English-only.

The implementation should make it possible to add approved Norwegian legal text later.

Remember: GDPR transparency requires information about personal-data processing to be clear, understandable and accessible. This is separate from a blanket requirement that the dashboard itself must be Norwegian.

---

# STEP 16 — Testing

Add or update automated tests.

At minimum test:

1. English renders correctly.
2. Norwegian Bokmål renders correctly.
3. Missing Norwegian key falls back to English.
4. Language selection persists.
5. Login/register language behavior works.
6. Protected dashboard routes respect locale.
7. Dynamic values are not accidentally translated.
8. Date/number formatting behaves correctly.
9. No visible translation keys appear.
10. Language selector is accessible.
11. Existing functionality continues to work.

If the project has component tests, add representative tests.

If the project has E2E tests, add at least one E2E language-switching flow.

Do not weaken or delete existing tests.

---

# STEP 17 — Search the codebase for hard-coded UI strings

After implementing the translation system, scan the application for hard-coded user-facing strings.

Look especially for:

```text
"Save"
"Cancel"
"Delete"
"Settings"
"Dashboard"
"Loading..."
"Something went wrong"
"No results"
"Create"
"Edit"
"Search"
"Email"
"Password"
```

Also inspect:

- toast messages
- alert messages
- validation messages
- modal content
- empty states
- table headers
- button titles
- aria-labels
- placeholders
- tooltips

Do not blindly replace strings inside:

- API requests
- database fields
- CSS
- code identifiers
- logs
- internal developer messages
- third-party library configuration

Use judgement.

---

# STEP 18 — Build and validation

Run the project's normal validation commands.

At minimum, where available:

- TypeScript check
- Lint
- Unit/component tests
- E2E tests
- Production build

Fix errors introduced by the implementation.

Do not leave TypeScript errors or broken builds.

---

# STEP 19 — Review the implementation

Before finishing, perform a final audit.

Confirm:

- [ ] English remains complete.
- [ ] Norwegian Bokmål is available.
- [ ] Language selector works.
- [ ] Preference persists.
- [ ] Authenticated dashboard respects locale.
- [ ] Signup/login supports locale.
- [ ] No raw translation keys are visible.
- [ ] Missing translations fall back safely.
- [ ] Dynamic customer content is not translated accidentally.
- [ ] Dates/numbers are locale-aware.
- [ ] Accessibility is maintained.
- [ ] Existing tests still pass.
- [ ] Production build passes.
- [ ] No unnecessary dependency was introduced.
- [ ] No Nynorsk work was added unnecessarily.
- [ ] Legal/privacy text was not modified without source/approval.

---

# Important implementation constraint

Do not rewrite the application architecture just to add i18n.

Do not migrate frameworks.

Do not replace the existing authentication system.

Do not redesign the dashboard.

Do not modify backend business logic unless required to persist the language preference.

Do not change database schemas unless necessary.

Do not change pricing, billing logic, chatbot behavior, lead behavior, or AI behavior as part of this task.

Keep the implementation focused on localization.

---

# Git / change management

Before making changes, inspect the current git status.

Do not overwrite unrelated uncommitted work.

At the end provide:

1. Summary of changes
2. Files changed
3. Dependencies added, if any
4. Tests run
5. Build result
6. Remaining English-only areas
7. Recommended next steps

Do not commit or push unless explicitly asked.

---

# Important instruction for Claude Code

Do not assume that the production site URL being supplied means you can inspect the authenticated dashboard through a normal HTTP request.

The source repository is the source of truth.

First inspect the repository and existing implementation.

If there is uncertainty about architecture, locate the relevant code rather than guessing.

Use the project's existing patterns wherever possible.

The final result must be production-quality and maintainable.
