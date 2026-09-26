# Handling data subject requests

Internal document. People can ask to access, correct, delete, restrict, port, or object to the
processing of their data, and can withdraw consent (GDPR art. 15–21). Requests reach us at
post@mielikkix.no or in any other form. There is no required format and no fee.

**Deadline: one month from receipt.** It can be extended by two more months for complex requests, but
you must tell the person within the first month and explain why. Log every request (template below).

## 1. First: whose data is it?

| Requester | Our role | What to do |
|---|---|---|
| An account holder (customer business owner or staff) | Controller | Handle it yourself (section 2) |
| A visitor to mielikkix.ai, a demo requester, or someone who chatted with *our own* chatbot | Controller | Handle it yourself (section 2) |
| A **customer's** website visitor, caller or reviewer | **Processor** | **Don't handle it directly.** Within 5 working days, forward it to that customer's account owner and tell the requester you've done so and who the controller is. Help the customer if they ask (section 3). |

## 2. Verify identity
- Confirm the request comes from the email address on the account, for example by replying to that
  address and asking for confirmation.
- Never send data to a different address than the one on file.
- Ask for only as much extra proof as you need. Don't collect new identity documents unless there is
  real doubt.

## 3. How to carry out each request

| Right | Account holders (self-service first) | Visitors etc. (manual) |
|---|---|---|
| Access / portability (art. 15, 20) | Dashboard → Chatbot Settings → Privacy & data → **Download my data** (`GET /api/account/export`, JSON) | Query by email in `leads` / `conversations` / `tickets`; send as JSON |
| Erasure (art. 17) | **Delete my account** (30-day grace, then `account_service.purge_due`) | Customer uses Leads → **Erase all data for this person** (`POST /api/chat/visitors/erase`). For our own tenant, do the same from Mielikkix's own dashboard |
| Rectification (art. 16) | Settings pages | Edit the row |
| Withdraw marketing consent (art. 7(3), 21(2)) | Privacy & data toggle, or the one-click unsubscribe link | n/a |
| Objection / restriction (art. 18, 21) | Assess case by case. Record the decision and why | Same |

After erasure, minimised consent records are kept for 3 years (see
[retention-schedule.md](retention-schedule.md)). Tell the requester this and the reason (demonstrating
compliance). That exception is allowed under art. 17(3)(e).

## 4. Reply
- Confirm what you did, in the language they wrote in (English or Norwegian).
- If you refuse or only partly comply, say why and tell them about their right to complain to
  Datatilsynet (or the ICO in the UK).

## Request log template

```
ID:              DSR-YYYY-NNN
Received:        date, channel
Requester:       (as little as needed, e.g. "account holder, email on file")
Our role:        controller / processor -> forwarded to tenant ... on (date)
Right(s):        access / erasure / ...
Identity check:  how, date
Due date:        received + 1 month (extended to ...: reason)
Actions taken:   
Reply sent:      date
Notes:           
```
