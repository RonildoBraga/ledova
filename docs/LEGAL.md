# Legal positions taken without advice

Five questions the project depends on — four on how it must behave, one on the
licence it is published under. **Nobody qualified has been asked any of them.**
This document records the position the project takes on each, what it is built
on, and what would show it wrong — so that the position is a decision rather
than a silence, and so that the day advice is affordable
the questions are already written.

Nothing here is legal advice or a legal opinion. It is the owner's reading of
primary sources, written down.

Questions 1 to 4 arise under the Corporations Act 2001 (Cth) and question 5
under the project's own licence. Read the provision before relying on a summary
of it: [the Act on the Federal Register of
Legislation](https://www.legislation.gov.au/C2004A00818/latest/text), and
[LICENSE](../LICENSE), which is short.

## What bites now, and what does not

**The first four do not reach their stated triggers today**: the platform runs
on a local chain or a supported
testnet, with synthetic data, and has never held a real security, a real
investor's money or a real company's register. The chain guards refuse any
mainnet chain id and mainnet configuration is absent from the repository. A
question about how a register must be kept is not engaged by a register of
fictional members.

Each question therefore has a **trigger** — the thing that would have to happen
before it matters — and they are not the same thing:

| # | Question | Triggered by |
| --- | --- | --- |
| 1 | s169(3) retention of former members | The first real company's first real member |
| 2 | s168, who is obliged to keep the register | The same moment, plus the terms between operator and issuer |
| 3 | Evidence retention period | The first real identity document held |
| 4 | Operating without an AFSL | The first offer of a real security to a real investor |
| 5 | Who "we" is in the licence's Competing Use test | Someone offering a competing service, or Blueberry Money beginning to operate |

Question 5 does not wait on real investors: the repository is already published
under the licence. A fork alone does not establish a Competing Use; the question
concerns the use made of the software and the relationship between its
Licensor and operator.

Questions 1 to 3 are ones a careful reader can settle from primary sources, and
the positions below do that. Question 5 is not settled by this document.
**Question 4 is the one where being wrong is an offence rather than a defect**,
and the position on it is to not reach its trigger.

## 1. Section 169(3): members who ceased in the last seven years

**What the section says.** The register must include, for each person who
stopped being a member within the last seven years, the information the register
held about them and the date they stopped. The Act expressly permits those
entries to be **kept separately** from the rest of the register.

**What the code does.** Current members are derived from on-chain balances;
former members are stored in `FormerHolder`, written by the six-hourly
`Transfer` fold, and exported as their own section of the register CSV.
`FORMER_MEMBER_RETENTION_DAYS` defaults to 2557 and the service refuses to fold
or purge below it. [ARCHITECTURE.md](ARCHITECTURE.md#former-members) describes
the mechanism.

**The position.** A derived current-holders view does not on its own satisfy
169(3), so the stored record exists. Keeping it separately is what the section
contemplates rather than a departure from it, which is why the export has two
sections rather than one merged list.

**What would show this wrong.** That a derived register satisfies 169(3) after
all — in which case the table is surplus and costs almost nothing. The
asymmetry is the whole reason to build it: being wrong in this direction wastes
a table, and being wrong in the other direction means the record that was
supposed to exist for seven years was never kept.

**The unresolved part is not the retention, it is the completeness.** The fold
reads `Transfer` events, so it sees every movement the chain records. What it
cannot see is a member who ceased before the class was deployed on this
platform. A company migrating an existing register onto Ledova brings history
the fold cannot reconstruct, and nothing imports it.

## 2. Section 168: who is obliged to keep the register

**What the section says.** A company must set up and maintain a register of its
members. The obligation is expressed as the company's.

**What the code does.** The operator console names the deployment mode and, for
each active company, who keeps the register on that deployment. It states that
fact and stops: it does not assert who carries the obligation. Every relation on
the spine `Company -> ShareToken -> {ShareIssuance, ShareIssuanceRequest,
CapitalIncreaseRequest, Offering, TransferOrder}` is `PROTECT`, so an issuer
with delete permission on its own company cannot destroy the register as a side
effect of deleting it.

**The position.** The company carries the obligation and the platform keeps the
register as its agent. That is the plain reading, and it is also the only
reading under which `single_issuer` and `registry` are two configurations of one
product rather than two different legal arrangements.

**What this leaves undone, and it is not a legal question.** An agency
relationship has to exist in the terms between the operator and each issuer.
There are no such terms. That is a document to write, not advice to buy, and it
is the gap to close first because it is free to close.

**The export trail is the other gap.** Each register export writes one
application log line naming the requesting user's primary key and the row count.
There is no export audit model, nothing queryable, and no retention beyond
whatever the deployment keeps its logs for — while every download is a full
sheet of members' residential addresses. If the operator carries any
record-keeping obligation over the register, this is where it is thinnest.

## 3. The evidence-retention period

**What the sources say.** Two separate obligations land on seven years for
records of this kind: the Corporations Act's financial-records provision, and
the AML/CTF customer-identification record requirements. Seven years is the
conventional Australian answer and the reason 2557 days was chosen.

**What the code does.** `CLASSIFICATION_EVIDENCE_RETENTION_DAYS` defaults to
2557 and is deploy-time rather than admin-editable, because purging is
irreversible. The clock is `RETENTION_CLOCK`: `reviewed_at` for a rejected,
revoked or withdrawn claim, `expires_at` for a verified one, and a submitted
claim has no clock and is never swept. `0` retains indefinitely.
`FORMER_MEMBER_RETENTION_DAYS` is independent and refuses to go below 2557.

**The position.** Seven years, from review or expiry. The basis is the
convergence of the two obligations above rather than a considered view of which
one governs, and that is the weakness: they are different obligations with
different triggers, and it is possible that neither runs from the moment this
code measures from.

**What would show this wrong.** A period that runs from the end of the
relationship rather than from the review. That is a larger change than the
length — the model does not record a relationship-ending event at all — and it
is the answer to watch for rather than the number.

**Which way to be wrong.** Keeping evidence too long is a privacy exposure;
destroying it too early is a compliance failure that cannot be undone. Where the
two conflict, the code keeps the evidence, which is the recoverable direction.

## 4. The excluded category, and why this one stays unanswered

**The question.** What would allow an operator to run this platform without an
Australian financial services licence? The wholesale-client and
sophisticated-investor exceptions — s708 for offers, s761G for financial-product
advice — mean no retail disclosure document is required for offers made only to
investors who qualify. Whether that is the right exception, and whether it
covers everything this platform does, is a different question from whether the
classification is recorded correctly.

**What the code does.** `InvestorClassification` carries four categories and
deliberately not a fifth:

| Category | Provision |
| --- | --- |
| `product_value` | s708(8)(a) |
| `accountant_certificate` | s708(8)(c) |
| `professional_investor` | s708(11) / s761G(7)(d) |
| `associated_person` | s708(12) |

The experienced-investor category, s708(10) / s761GA, is absent on purpose: it
is the only one that turns on the operator holding an AFSL, and there is no
evidence this deployment does. That absence is the clearest statement in the
code of the position being described here.

**The position: do not reach the trigger.** This is not a question to answer by
reading, and the honest thing is to say so rather than to assemble a confident
paragraph out of free sources. Operating a financial services business without a
licence where one is required is an offence, not a defect — the cost of being
wrong is not symmetrical with anything else in this document. So the position is
that the platform stays on testnet with synthetic data until someone qualified
has answered this, and the chain guards are what make that a mechanism rather
than an intention.

**When it is worth paying for, it is one scoped question, not open-ended
advice.** That is what this document is for: the categories are enumerated, the
provisions are named, the gaps are listed, and what the software actually does
is written down. A fixed-fee opinion on a question that precise costs a small
fraction of an open engagement that starts with explaining the product.

**One dated fact to watch.** The `accountant_certificate` category depends on
who counts as a qualified accountant, which is set by an ASIC legislative
instrument rather than by the Act — ASIC Corporations (Qualified Accountant)
Instrument 2016/786, due to sunset on 1 October 2026 and proposed to be remade.
[RG 154](https://www.asic.gov.au/regulatory-resources/find-a-document/regulatory-guides/rg-154-certificate-by-a-qualified-accountant/)
is the guide, and the thresholds a certificate attests to are in it. If the
remade instrument changes who may certify, this category's evidence rules change
with it.

## 5. The licence's Competing Use test, and who "we" is

**The question.** The Functional Source License defines a Competing Use as
making the Software available to others in a commercial product or service
that: (1) substitutes for the Software; (2) substitutes for any other product
or service *we* offer using the Software **that exists as of the date we make
the Software available**; or (3) offers the same or substantially similar
functionality as the Software. In each, *we* is the Licensor. The Licensor named
in [LICENSE](../LICENSE) is an individual. The company expected to operate
Ledova as hosted infrastructure is Blueberry Money, a separate legal person
described in the README as a prospective operator. The relationship between
them and the existence of the relevant service at publication are separate
questions under limb (2).

**What the documents do today.** `LICENSE` is FSL-1.1-ALv2 with
`Copyright 2026 Ronildo da Rocha Braga Junior`. The README names Blueberry Money
as sponsor and prospective first operator, and says sponsorship transfers no
ownership and no control. The repository contains no separate licence,
assignment or service agreement between the individual and the company. That
does not establish whether private agreements exist or determine ownership of
every contribution. The licence's trademark clause remains unchanged.

**The position recorded here.** The existing licence and named individual
Licensor remain unchanged. Limbs (1) and (3) provide separate tests from limb
(2), but this document does not decide whether a particular competing service
meets any of them. The question is retained for review before relying on that
interpretation or changing the operating arrangement.

**What remains unresolved.** The relationship between the individual and the
operator needs an explicit account. A written agreement could record the
company's rights and responsibilities; this document does not establish that
it would make the company's service one the Licensor offers. Limb (2)'s
publication-date condition is a separate question and cannot simply be omitted
because an agreement is later written. The terms must be considered for the
version of the Software concerned.

**Decisions this does not make.** A licence to the company and an assignment of
copyright are different arrangements. No assignment, new company licence or
change to the existing future Apache grant is made here. Any such proposal
needs the owner's decision on its actual terms and its effect on existing
rights; it should not be inferred from a documentation cleanup.

## Free and low-cost sources

None of these is advice, and none of them knows anything about this deployment.

- [The Act itself](https://www.legislation.gov.au/C2004A00818/latest/text).
  Sections 168, 169, 708 and 761G are short and readable.
- [ASIC's member register guidance](https://www.asic.gov.au/for-business-and-companies/companies/company-share-and-shareholder-rules-and-changes/members-register-requirements-and-changes)
  — what the register must contain, in plain language.
- [RG 154](https://www.asic.gov.au/regulatory-resources/find-a-document/regulatory-guides/rg-154-certificate-by-a-qualified-accountant/)
  on accountant certificates, and ASIC's regulatory guides generally, which are
  free and are what ASIC itself applies.
- AUSTRAC's published guidance for the customer-identification and
  record-keeping obligations behind question 3.

What does not exist, and is worth knowing rather than searching for: community
legal centres and legal aid do not take commercial financial-services work.

## Where these are recorded elsewhere

- [ROADMAP.md](ROADMAP.md) — the wholesale-only decision, the four
  classification categories and the deliberate absence of the fifth, under
  Decisions taken.
- [OPERATIONS.md](OPERATIONS.md) — the deployment mode and registrant, the two
  retention settings and the account-deletion position.
- [ARCHITECTURE.md](ARCHITECTURE.md) — the register's shape, the former-member
  fold, and the `PROTECT` spine that stops the register being deleted.
- [LICENSE](../LICENSE) and [README.md](../README.md) — the FSL terms, the
  Licensor named in them, and Blueberry Money's stated role as sponsor and
  prospective operator.
