# Personal data breach runbook

Internal document. A personal data breach is any security incident that leads to personal data being
destroyed, lost, altered, disclosed or accessed without authorisation, whether by accident or
unlawfully (GDPR art. 4(12)). Examples: a leaked database dump, an email sent to the wrong customer,
a bug that shows one tenant another tenant's leads, a lost laptop with production credentials, or a
compromised API key.

**The 72-hour clock starts when we become aware** that a breach has probably happened, not when the
investigation ends.

Incident owner: `{{VERIFY: name / role}}`. Deputy: `{{VERIFY}}`.

## 1. Detect and record (hour 0)
- Open a new entry in the breach log (template below) **immediately**, even if it later turns out not
  to be a breach.
- Write down when and how we found out.

## 2. Contain (first hours)
- Stop the leak: revoke keys, rotate `SECRET_KEY` / `TOKEN_ENCRYPTION_KEY` if exposed, disable the
  affected endpoint, restrict access to the VPS.
- Rotating `SECRET_KEY` logs everyone out, invalidates unsubscribe links, and stops old consent
  subject hashes from matching (see [retention-schedule.md](retention-schedule.md)). Record that you
  did it.
- Preserve evidence: copy logs before rotation or retention removes them.

## 3. Assess (within 24 h)
Answer and record:
- Which data categories and which tables are affected? Use [records-of-processing.md](records-of-processing.md).
- Whose data: our own customers (we are **controller**), or a customer's visitors and callers (we
  are **processor**)?
- How many people, and in which countries? `users.country` gives this for account holders.
- What's the likely risk to them: none/unlikely, a risk, or a **high** risk (for example passwords,
  special-category data, or data that enables fraud or identity theft)?

## 4. Notify

| Situation | Who | Deadline | How |
|---|---|---|---|
| We are controller and there is a risk to people | **Datatilsynet** | **72 hours** from awareness | Online breach notification form at datatilsynet.no |
| UK residents affected | **ICO** | 72 hours | ico.org.uk breach report |
| Indian residents affected (DPDP Act) | **Data Protection Board of India** and the affected people | Without delay, per the DPDP Rules `{{VERIFY: current deadline}}` | `{{VERIFY}}` |
| We are controller and there is a **high** risk to people | The affected people | Without undue delay | Email in plain language: what happened, likely consequences, what we did, what they can do, our contact |
| We are **processor** (a customer's end-user data) | The affected **customers** | **Without undue delay** (DPA § 4.6). The customer then decides on notifying Datatilsynet and their users | Email to the account owner with everything they need for their own notification |

If a notification isn't complete within 72 hours, send what you have and follow up. Record the reasons
for any delay.

## 5. Recover and learn
- Fix the root cause and add a regression test.
- Update this runbook, the retention schedule or the subprocessor list if the incident showed they
  were wrong.
- Close the log entry with a summary.

## Breach log template

Keep the log `{{VERIFY: where, e.g. a restricted folder}}`. Record **every** incident, including ones
that don't need reporting (art. 33(5)).

```
ID:                     BR-YYYY-NNN
Discovered (UTC):       
Discovered by / how:    
Start of breach (UTC):  
Description:            
Our role:               controller / processor (tenant: ...)
Data categories:        
Tables / systems:       
Number of people:       
Countries:              
Risk assessment:        none / risk / high risk, and why
Containment steps:      
Datatilsynet notified:  yes/no, date/time, case no., or why not
ICO / other notified:   
Customers notified:     who, when
Individuals notified:   yes/no, when, how, or why not
Root cause:             
Fix / follow-up:        
Closed (date, by):      
```
