# A Revolut Business payment draft, planned and then sent to sandbox

This uses the **Revolut Business API**, not the consumer/Personal Revolut app.
The sandbox is a test environment for Business; it is not a Personal API.
Production Business credentials are not supported by this prototype yet.
For the live Business account, start in the [Revolut Business web app settings](https://business.revolut.com/settings)
under **APIs → Business API**, not the consumer developer sandbox. The
[Business API reference](https://developer.revolut.com/docs/api/business)
documents bearer authentication and the `READ`, `WRITE`, and `PAY` scopes.
Personal Revolut is tracked separately as a fast-follow.

`examples/revolut-business/prototype.bl` turns checked values into the request
body that creates a **payment draft** for an external beneficiary. It is a
planner: it produces a value you read, and it sends nothing.

`examples/revolut-business/sandbox.bl` is the wire under that value. It reads
accounts and counterparties and creates the draft — against the sandbox host
only, and never a payment.

```
examples/revolut-business/prototype.bl        the planner — no network at all
examples/revolut-business/sandbox.bl          the sandbox client — two reads, one draft
test/bl/revolut_business_prototype_test.bl    both contracts
```

## The request it plans

```
POST /payment-drafts
```

Body:

```json
{
  "title": "September contractors",
  "payments": [
    {
      "account_id": "2e6de1bf-97ad-478d-aad1-9d7a3cdf70cb",
      "receiver": {
        "counterparty_id": "a15bcac4-dd42-45ed-a828-6806ccc8bb7e",
        "account_id": "2bf609f4-9825-4401-b6f7-960c61f8bee0"
      },
      "amount": 42.75,
      "currency": "EUR",
      "reference": "INV-7"
    }
  ]
}
```

The source of truth is the official reference:

- create a payment draft — <https://developer.revolut.com/docs/api/business/operations/create-payment-draft>
- the payment-drafts guide — <https://developer.revolut.com/docs/guides/manage-accounts/transfers/payment-drafts>
- the Business API index (base URLs and scopes) — <https://developer.revolut.com/docs/api/business>

Two facts that shape the planner come from that document:

- **One payer per draft.** *"You can specify only one account ID for multiple
  payments in the same payment draft."* `account_id` is therefore an argument of
  the draft, not of a payment, and every payment in the body carries that one
  account.
- **The receiver's account is often required.** `receiver.account_id` is optional
  only while the counterparty has exactly one payment method. A counterparty with
  two accounts, or an account and a card, is ambiguous without it, so the planner
  requires it always.

`GET /accounts` and `GET /counterparties` are the read operations that return
these identifiers. `POST /transfers` moves money between accounts you own, which
makes it the wrong endpoint for paying someone else.

## A draft is not a payment

The endpoint creates a draft. It sits in the Revolut Business app until a person
sends it for processing. That send starts payment processing; an approval
process can still hold it for review. A draft can be deleted before then.

The scopes draw the same line. The Business API issues four:

| Scope | Grants |
| --- | --- |
| `READ` | `GET` operations |
| `WRITE` | update counterparties and webhooks, **issue payment drafts** |
| `PAY` | initiate or cancel transactions and currency exchanges |
| `READ_SENSITIVE_CARD_DATA` | retrieve sensitive card details |

This offline planner needs no token. `POST /payment-drafts` uses `WRITE`, not
`PAY`; `GET /accounts` and `GET /counterparties` use `READ`. The sandbox client
uses exactly those two — `READ` for the reads, `WRITE` for a draft — and asks
for nothing else, because sending a draft for processing stays a separate human
action in the app.

## Verify before you plan

The planner cannot tell a right payee from a wrong one. It validates shape —
non-empty identifiers, a positive amount in exact cents, a two-place decimal —
and shape is not identity. Read the payer account, the counterparty, the
counterparty's account and the reference back from the API or from the invoice,
match them by eye, and only then pass them in. A wrong value planned correctly
is still a wrong payment.

Amounts enter as **integer cents** (`4275`) or as a strict decimal string
(`"42.75"`). A float is refused on purpose: many decimal amounts (such as
`0.1`) have no exact binary representation, and nearly right is wrong for money.

## Using it

```clojure
(ns my.payments
  (:require [revolut-business.prototype :as rb]))

(def plan
  (rb/plan-draft
    {:account-id "2e6de1bf-97ad-478d-aad1-9d7a3cdf70cb"
     :title "September contractors"
     :payments [{:counterparty-id "a15bcac4-dd42-45ed-a828-6806ccc8bb7e"
                 :beneficiary-account-id "2bf609f4-9825-4401-b6f7-960c61f8bee0"
                 :amount "42.75"
                 :reference "INV-7"}]}))
```

The value has the request line and body, plus a preview:

```
{:method "POST"
 :path "/payment-drafts"
 :scope "WRITE"
 :currency "EUR"
 :account-id "2e6de1bf-97ad-478d-aad1-9d7a3cdf70cb"
 :title "September contractors"
 :amounts ["42.75"]
 :total-cents 4275
 :body-json "{\"title\":\"September contractors\",\"payments\":[…]}"
 :preview "POST /payment-drafts  (draft — nothing is sent)\n  …  EUR 42.75  ref \"INV-7\"\n  WRITE scope: …"}
```

`:body-json` is the wire body. Every string in it crosses through
`bl.json/encode`, so a reference containing a quote, a brace or a newline comes
back byte-for-byte and adds no structure. The amount is the one value written
raw: JSON has no exact-decimal type and the API wants a number, so
`cents->decimal` emits digits and one dot and the body carries `"amount":42.75`
— not `"42.75"`, and not a float.

`:preview` says the same thing in words, for the human who approves the send.

Check both with their tests:

```sh
bl test test/bl/revolut_business_prototype_test.bl
```

## What the planner refuses

- an empty or whitespace-padded account id, counterparty id, beneficiary account
  id or reference — a padded id is a different id to the API;
- a missing beneficiary account id, because the counterparty may be ambiguous;
- a float amount, a zero amount, a negative amount, or a decimal with more than
  two places;
- an empty payment list.

Each refusal raises with a message that names the field to fix.

## Sending the draft: the sandbox client

`sandbox.bl` owns three operations and no more:

| Call | Wire | Scope |
| --- | --- | --- |
| `(sandbox/accounts token)` | `GET /accounts` | `READ` |
| `(sandbox/counterparties token)` | `GET /counterparties` | `READ` |
| `(sandbox/create-draft plan token)` | `POST /payment-drafts` | `WRITE` |

The host is a value in the source and not an argument:

```
https://sandbox-b2b.revolut.com/api/1.0
```

No call accepts a host, so no caller and no typo can aim this client at
`https://b2b.revolut.com/api/1.0`. That is also why there is no
send-for-processing call: the draft waits in the app for a person, so the
operation that sends it is absent rather than merely guarded.

### The token is an argument, and it stops at the wire

Every call takes an access token. The client does not obtain one, refresh one,
write one to a file, or return one — the token enters the transport request and
stops there. Responses still contain financial data and should not be logged
indiscriminately. Obtain a sandbox bearer access token through Revolut's
Business API setup flow and pass it to the call. This prototype does not
implement client assertions, OAuth exchange, refresh or credential storage.

### Every outcome is a value

```
{:ok true  :status 200 :data [...accounts…]}
{:ok true  :status 201 :data {…} :id "draft-id"}
{:ok false :status 204 :error :no-content :detail "…"}
{:ok false :status 0   :error :transport  :detail "…"}
{:ok false :status 400 :error :http :detail "Revolut returned a non-success HTTP status"}
```

Nothing raises on a wire failure, and nothing reports an empty success.

- **`204` is not a draft.** The API answers 204 for *no payments provided*.
  `create-draft` reports `:no-content`, and it refuses a plan with an empty
  payment list before the wire, so a 204 means a request that passed that guard
  and still created nothing.
- **`0` is not an empty list.** Status 0 is the transport saying nobody
  answered: a distinct `:transport` error, never a page with no rows. A 2xx whose
  body is not JSON is `:empty`, also an error.
- **Errors retain status, not raw provider text.** A provider or transport error
  could echo the bearer token. The client discards response bodies on failure;
  use the status to diagnose access and request failures without leaking secrets.
- **Nothing retries.** A retried `POST /payment-drafts` is a second draft, so a
  caller who wants a retry owns the idempotency question.
- **A 2xx with no `id` is not a created draft.** A draft that cannot be named
  cannot be read back or deleted, so the response is refused.

### Paging

`GET /counterparties` is paged: the cursor is the `created_at` of the last
counterparty of the previous page, sent back as `created_before`. The client
sends no query parameters, so it reads the first page and stops. `GET /accounts`
is not paged. A business with more counterparties than a page holds needs the
walk the API guide describes, driven by a caller that keeps the cursor.

### Testing it without a socket

Both contracts run in one command:

```sh
bl test test/bl/revolut_business_prototype_test.bl
```

No test opens a socket. Each call takes an optional transport — a function from
request to response — so a test hands in one that records the request and
answers what the test wrote, and the method, the URL, the `Authorization`
header, the content type and the body are pinned exactly. The default transport
is the real one (`connector.http/ensure-apps` plus `httpc/request`), and the
suite never exercises it.

## The boundary

Two boundaries, drawn in different places.

**The planner** holds no token, opens no socket and names no host. It knows the
path and the method the API documents, and nothing about where that API lives.
Everything it returns is a value a person reads.

**The sandbox client** holds a token for the length of one call, names the
sandbox host and no other, and can create a draft. It cannot send a draft for
processing, cannot cancel a transaction, and cannot reach production.

Both carry recipient identifiers and payment references, which are sensitive
financial data: review or store a plan, a response, or a log of either in an
appropriately protected place.

## Live Business credential handoff (not implemented yet)

In the live Business web app, confirm **Settings → APIs → Business API** is
available to your account. Do not enable `PAY` or submit a payment for this
prototype. Do not paste a private key, access token, refresh token or
client assertion into chat, source files, a shell command argument or a commit.

The production-auth follow-up will accept a **path to a local private key**,
not the key bytes in a project file. The intended location is
`~/.config/beam-lisp/revolut-business/private.pem` in a directory readable only
by your user (`0700` directory, `0600` file). This is an interface plan, not
a working setting today: placing a key there does not connect the current
sandbox-only client. Upload only its **public X.509 certificate** to the
Business API settings. Keep the issued client ID and exact redirect URI in a
separate local configuration when the auth flow defines its callback; neither
belongs in this draft plan. Do not guess a redirect URI before that flow is
implemented.

Production support must implement the official certificate/client-assertion
exchange, initial consent, expiring access-token refresh, secure token storage,
and an explicit production opt-in. Its first operation will be a `READ` account
probe that reports auth failures rather than treating them as empty accounts.
Only after independently verifying recipient, account, reference and amount
will the client offer a `WRITE` payment **draft**; it will not request `PAY` or
send that draft for processing.

## Next steps

- **Authentication** — a JWT client assertion trades for an access token and a
  refresh token keeps it alive, so a caller stops passing a token in by hand.
  A token belongs in a store, never in a plan.
- **Reading a draft back** — `GET /payment-drafts` and
  `GET /payment-drafts/{id}` are the read side of the `id` a create returns.
- **A longer counterparty walk** — page `GET /counterparties` with
  `created_before` until a page comes back short.
- **A review step** — the preview is the artifact a person approves, which is
  what keeps the draft meaningful.
