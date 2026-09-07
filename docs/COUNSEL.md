# Questions for counsel

Four questions the project's own documents flag as needing legal advice, stated
here in one place so they can be sent as a brief rather than found by reading
three documents. Each one gives the question in the statute's terms, what the
code does today, and what each answer would change.

Nothing here is a legal opinion or a position the project has taken. Where the
documents already record a decision — the wholesale-only constraint, the
2557-day retention default — it is recorded as a decision made without advice,
which is part of what the question asks about.

The answers are recorded as owner decisions on
[#115](https://github.com/RonildoBraga/ledova/issues/115) when they come back,
and this document is updated to point at them.

Statute references are to the Corporations Act 2001 (Cth).

## 1. Section 169(3): members who ceased in the last seven years

**The question.** Section 169(3) requires the register of members to keep, for
each person who has ceased to be a member within the last seven years, the
information the register held about them and the date they ceased. Can a
register derived from current on-chain balances satisfy that requirement, or
does it oblige the platform to keep a stored record of holdings that ended?

**What the code does today.** The register is derived, not stored. It is built
from current holders — the balance a wallet holds now, joined to the identity
behind that wallet — and a holder whose balance reaches zero simply stops
appearing. There is no record of a holding that ended: the read-model knows
about allotments that happened, not about holdings that stopped. `GET
/api/v1/tokens/{uuid}/register/export/` writes a CSV shaped for section 169,
whose twelve columns are Name, Residential address, Wallet address, Holder
type, Class, Shares held, Percentage of issued supply, Balance source, Identity
source, Date entered, Whitelist status and Amount paid — and every row in it is
a current member.

The register is complete only while allotment is the only way shares move,
which holds today because the trading write paths are flag-gated and
`resolve_transfer_asset` refuses a tokenized security. The documents state
plainly that relaxing either guard makes a transferee invisible to the
register.

**What each answer would change.**

- *A derived current-holders register does not satisfy 169(3).* The platform
  builds a stored record of former holders per share class, fed from the same
  `Transfer`-log fold the register reconciliation uses: a holder whose balance
  reaches zero is written with the date it reached zero, exported under a
  separate heading, retained seven years. This is being designed now on the
  assumption the answer is this one, because the shape of the register's data
  model is being settled and it is cheaper to design for it than to retrofit
  it.
- *It does satisfy 169(3), or the obligation does not bite this way.* The
  designed table is dropped and the register stays derived.
- *It satisfies 169(3) only under conditions* — for example only while every
  movement is an allotment the platform records. Then the conditions become
  the trigger for building the stored record, and the documents record them
  where the guards are described.

## 2. Section 168: who carries the obligation to keep the register

**The question.** Section 168 obliges a company to set up and maintain a
register of members. On this platform, one party operates the software, another
is the company whose members are registered, and in one deployment shape they
are the same party. Who carries the section 168 obligation: the company, with
the platform acting as its agent, or the platform operator in its own right?

**What the code does today.** The platform states the fact and declines the
conclusion. The operator console names the deployment mode (`registry` or
`single_issuer`) and, for each active company, who keeps the register on that
deployment. The documentation says in as many words that this is a statement
about the deployment and not an assertion about who is obliged — that the
question belongs to the issuer and its advisers.

The register is also protected against deletion through the API. Every relation
on the spine `Company -> ShareToken -> {ShareIssuance, ShareIssuanceRequest,
CapitalIncreaseRequest, Offering, TransferOrder}` is `PROTECT`, so an issuer
with delete permission on its own company cannot destroy the register as a side
effect.

**What each answer would change.**

- *The company carries it, with the platform as agent.* An agency
  relationship needs to exist in the terms between the operator and each
  issuer, and the platform's obligation is to the issuer rather than to the
  registry. What the software does need not change; what the contracts say
  does.
- *The operator carries it.* The operator's own record-keeping, retention and
  production obligations attach to the register directly, which bears on the
  export trail below and on what happens to a company's register when it
  leaves the platform.
- *It depends on the deployment shape.* Then `registry` and `single_issuer`
  are not two configurations of one product but two positions, and the
  documents say which is which.

Whatever the answer, one gap is already recorded as owed rather than answered:
each register export writes a single application log line naming the requesting
user and the row count, and nothing more. There is no export audit model,
nothing queryable, and no retention beyond whatever the deployment keeps its
logs for. Every download is a full sheet of members' residential addresses.

## 3. The evidence-retention period

**The question.** How long must evidence supporting an investor's wholesale or
sophisticated classification be kept, and from when does the period run? The
platform holds documents an investor supplied to support a classification claim
— accountant certificates and, under a decision taken but not yet built,
payslips.

**What the code does today.** `CLASSIFICATION_EVIDENCE_RETENTION_DAYS` defaults
to `2557` — seven years — and is a deploy-time setting rather than an
admin-editable field, because purging is irreversible. The documents call the
value a placeholder rather than advice, and name Australian financial-record
and AML/CTF customer-identification obligations as the constraints to confirm
it against. `0` retains indefinitely and purges nothing.

The clock runs from `reviewed_at` for a claim that was rejected, revoked or
withdrawn, and from `expires_at` for one that was verified — so a revoked claim
runs from its review rather than from a stale expiry left on it. A claim whose
clock is not stamped is never swept.
A nightly job deletes the bytes; no status column records the purge, because a
cleared `evidence_file` is the record. `evidence_file_size` and
`evidence_mime_type` survive as content-free metadata.

Two related positions are already taken. Deleting an account does **not** purge
evidence early: `delete_account` is a tombstone that never touches the
classification, on the reasoning that a fixed retention period exists precisely
to outlive the subject's wishes. And `users.InvestorClassification` is named in
`RETAINED_AFTER_ROW_DELETE` with the reason that its evidence has a statutory
retention horizon and outlives its row deliberately.

A decision taken but not yet built attaches payslips to the same clock: a
payslip is reviewed evidence for a classification claim, read by the platform
owner and operations and never by the issuer, retention inheriting
`CLASSIFICATION_EVIDENCE_RETENTION_DAYS` with the same carve-out and a shorter
purge for payslips never attached to a claim.

**What each answer would change.**

- *Seven years is right.* The default stands and stops being a placeholder;
  the documentation says so and names the obligation it comes from.
- *A different period.* The setting changes, and so does the payslip design
  that inherits it. Because the value is deploy-time, a change is a deploy and
  a review rather than a form submit — deliberately.
- *Different periods for different evidence.* Then one clock is not enough,
  and the classification and payslip retentions separate before the payslip
  store is built.
- *The period runs from something other than review or expiry* — the end of
  the relationship, say. Then the clock's basis changes, which is a larger
  change than its length: the current clock is stamped at review, and a
  relationship-ending event is not a thing the model currently records.

## 4. The excluded category the operator relies on

**The question.** What allows the operator to run this platform without an
Australian financial services licence? The documents record a decision made
without advice: the first offerings are made only to investors who qualify
under the wholesale-client and sophisticated-investor exceptions — section 708
for offers and section 761G for financial-product advice — so no retail
disclosure document is required. The question is whether the exception the
operator relies on is the right one and whether it covers what the platform
actually does.

**What the code does today.** The classification model carries four categories
and deliberately not a fifth:

- `product_value` — s708(8)(a)
- `accountant_certificate` — s708(8)(c)
- `professional_investor` — s708(11) / s761G(7)(d)
- `associated_person` — s708(12)

The experienced-investor category, s708(10) / s761GA, is **absent on purpose**:
it is the only one that turns on the operator holding an AFSL, and there is no
evidence this deployment does. That absence is the clearest statement in the
code of the position being asked about here.

`associated_person` is also treated differently from the other three, on the
reasoning that s708(12) is about one issuer's offer rather than about a market
in shares, so it is not an unscoped predicate about an investor.

Enforcement is staged: the classification is recorded today and the eligibility
gate that enforces it is Phase 2 work. Nothing in the code enforces the
wholesale-only constraint yet.

**What each answer would change.**

- *The exception relied on is right and covers the platform's activity.* The
  documents record it as advised rather than assumed, and the wholesale-only
  constraint stops being a decision taken without advice.
- *A licence or an authorised-representative arrangement is needed.* That is a
  change to what the operator is, not to what the software does — though it
  would make the experienced-investor category expressible, which is the one
  the code deliberately omits.
- *The exception is right but the platform's activity exceeds it* — for
  example once secondary transfers between investors are enabled, which is
  planned. Then the answer names the boundary, and the boundary becomes a gate
  in the code rather than a note in a document.

## Where these are flagged in the documents

- [ROADMAP.md](ROADMAP.md) — the past-members gap and the section 168 question
  in Phase 1; the 169(3) retention item in Phase 2; the retention period and
  the wholesale-only decision under Decisions taken; the four classification
  categories and the deliberate absence of the fifth.
- [OPERATIONS.md](OPERATIONS.md) — the deployment mode and registrant, which
  states who keeps the register and not who is obliged to; the retention
  setting and the account-deletion position.
- [ARCHITECTURE.md](ARCHITECTURE.md) — the register's shape, the condition
  under which it is complete, and the `PROTECT` spine that stops it being
  deleted.
