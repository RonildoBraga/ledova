# Practices

How work is done in this repository. It is written for whoever is doing it,
person or model, and no part of it is specific to one tool.

**Discipline** below is the method that applies to all of it. The sections after
it are the kinds of work themselves: what each answers, how it proceeds, what it
produces.

**Kinds are separated by method, not by topic.** Two kinds belong apart when they
use different tools or establish their conclusions differently. Backend and client
work differ in toolchain and in what can go wrong. Reading a document and running
a procedure differ in method. Dashboard and mobile work do not differ that way:
they share `packages/shared`, and a change there is a change to both.

## Discipline

The gates in [GATES.md](GATES.md) encode what can be checked mechanically. This
is the part that cannot be: how to establish that a change does what it claims.
Every rule here was bought by a specific failure, and [TRAPS.md](TRAPS.md) holds
the individual cases under **Test traps** and **Measurement traps**.

**Red-prove the claim, and if it will not go red, say why in the body.** Revert
the fix, watch a *named* test fail, restore it, watch it pass, and put both
directions in the body. Where a meaningful failure genuinely cannot be
demonstrated, that is a sentence you owe a reader, not a step to skip. A test
written after a fix and
never seen to fail describes the code rather than checking it. Seventeen tests in
one file once asserted that a provider's error text reached the caller: they
pinned the leak they existed to prevent, and only rewriting them exposed it.

**An assertion of absence needs a control.** Before concluding that a row is
hidden, a refusal fired, or a count is zero, show the case that would have made it
visible, allowed or non-zero. "No rows returned" proves nothing when no rows
existed to hide. Six assertions in a merged file compared, differed and passed for
weeks because a local helper named `fail` shadowed the method they raised through,
and nothing had ever asked whether they could fail.

**A count that agrees with your first hypothesis is where to look harder.** Three
hundred and fifty-five test failures that were entirely the harness. The same
number twice, where the tell was that a hundred and fifty-nine of them shared one
status code rather than in the total. A gate that appeared to catch a planted bug
and was in fact reporting a *pinned* count shrinking below its pin. Ask what
result would have shown you wrong, and check that instead.

**Certify only what you read, at the head you read it on.** A review line carries
the read that actually happened and no more. On a rebase, either prove the content
is unchanged and say how, or read the delta; never let a line follow a branch it
was not given at.

**Say what you did not check.** An unstated gap reads as a checked one. "Full
depth" and "proportionate, and I did not run the chain suite" are both fine; a
silent omission is not.

**Read the source, not the summary you were handed.** Summaries in this project
have been materially wrong about the size of a change, about who had reviewed
what, and about what a gate's own docstring says. Open the file.

**A deliberate scope is not a defect.** Before reporting that a check only looks
one way, read whether the source argues for it. The API type drift gate is
one-directional by design and says so; treating that as a bug would have broken
something already correct. A deliberate scope and an oversight look identical from
outside, and the costs of confusing them are not symmetrical.

**When the instrument was the problem, write that down.** Several of the most
useful findings here began as a wrong result the reporter caught in themselves: a
browser measured against a five-hour-old image, a network log still holding a
previous build's responses, a call graph that matched by bare function name.
Correcting it silently teaches nobody.

**If it can be checked mechanically, it belongs in `scripts/` rather than in
prose.** A rule that lives only in a document is a rule that will be broken
without anyone noticing. Every gate this repository has exists because a written
rule was not enough.

## Building

One issue, implemented, with a pull request. Scope stays at the issue: a defect
found on the way is filed, not folded in. Who may review and merge it, and which
paths the owner reserves, is policy rather than method and is stated under
**Review and merge** in [CONTRIBUTING.md](../CONTRIBUTING.md).

The body states what was measured, what could not be reproduced, and what was
deliberately not done. A body that only says what works is half a report.

### Backend

Django, DRF, PostgreSQL, Procrastinate, and the chain integration.

- Where anyone else is working, a migration number is claimed in a comment on the
  plan issue **before** it is pushed: two migrations have claimed the same number
  here. Working alone the claim is noise, but the graph still is not: where two
  migrations fork off one parent, the second to land re-points one dependency
  line in its rebase.
- Transactions open with `shared.db.atomic`, never bare `transaction.atomic`, and
  never through the bare `connection` proxy, which is the bypassing role. The
  connection-binding gate refuses both, including the import forms.
- A PostgreSQL-only trigger or policy is certified by the **full** PostgreSQL
  suite, not by the lane's own tests. A constraint on a status field additionally
  needs the real-chain suite on PostgreSQL, which skips silently elsewhere.
- A partial index over statuses is entered by every write that moves a row into
  its condition, not only by the writes that create one.
- A record is not blanked to fix a display. The status says what is true now; the
  field keeps what was true then.
- `black`, `isort` and `flake8` are not in the backend image, but CI runs them.

### Client

`packages/shared`, `dashboard/` and `mobile/`, together, because both clients
consume the shared package by design and a fix there fixes both.

- The dashboard is a **built image with no volumes**. `docker compose restart`
  serves stale code; only `docker compose build` changes it.
- React Native Testing Library v14 made `render` and the event helpers async. A
  forgotten `await` on a press before an **absence** assertion passes wrongly. The
  mobile config does catch it: `no-floating-promises` runs type-aware over
  `**/*.test.{ts,tsx}`, so lint is the check, not review.
- Nothing in this repository's development environment can render mobile. Mobile
  claims are data-path claims unless a person confirms on a device.
- A shared type that declares **required** a field the API never sends is drift;
  the reverse is deliberately not, and the type gate says so.
- The backend's own message reaches the person. Field errors arrive as
  `{"field": [...]}`; discarding them for a generic sentence has produced advice
  that could not work.

## Reviewing

A review answers whether a change does what it claims, at a stated head, to a
stated depth.

- **A line carries only the read that happened.** An identity line on a pull
  request nobody read asserts something false; do the read or decline.
- **A line belongs to one head sha.** After a rebase, either prove the content
  unchanged and say how, or read the delta.
- **Depth is stated**, and so is what was not checked. An unstated gap reads as a
  checked one.
- The body is checked against the diff. Bodies drift: a paragraph promising a
  follow-up that already merged, a sentence describing a constant since removed.
- On a rebase conflict, the other side's **commit** is read, not just the diff. A
  conflict is two intentions and the diff shows one.

The output is one comment whose first line is the verdict and the head sha.
Blocking is ordinary; a block stands until its author clears it on that pull
request.

## Driving the product

Someone opens the product in a browser against a running stack and reports what
happened. This has repeatedly found what the suite could not.

**First, prove which code is running.** Name the sha and show the running system
is built from it, by fetching what the browser was served or hashing the file
under test. Image age is an alarm; a file hash is an answer.

Environment traps that have cost real time:

- Clearing `localStorage` does not clear the session; it is cookie-based, and an
  old one carries you past a broken sign-in.
- A bare `python -c` takes the application role with no principal, so a row it
  cannot see may be present. `manage.py` takes the operator role and sees it.
- A stale network log hands back a previous build's responses.
- Your own probe requests appear in the capture as application traffic.

"Features work with policies bypassed" and "enforcement holds" are different
claims, and the report says which one it has. The stack and its fixtures are left
as found; they are the input to other work.

## Auditing

Four audits, kept apart because they establish things differently.

### Documents against code

Read-only. Three questions: what does this document assert that the code
contradicts, what does it require that nothing enforces, and what have recent
merges changed that it has not caught up with.

A finding is two quotes and two locations, then one sentence on what a reader
would wrongly conclude. Without both halves it is not a finding. No opinions and
no refactor proposals: they flood the report and it stops being read.

### Code against its rules

The enforcement that has not been written yet. Take a rule as stated, enumerate
every site it governs, say what the enumeration cannot see, and report the
violations. For each rule, answer whether it could be a script, and sketch the
check: several gates began exactly that way.

Prefer rules whose breach is invisible at runtime. Both databases work, the page
renders, the test passes, and the thing is still wrong.

### Procedures against a machine

This one **runs** rather than reads. A procedure whose only proof is that
somebody wrote it down is not a procedure: the most expensive defect this project
has had was operations text describing a database setting that nothing applied,
so a fresh stack could not start.

Run it exactly as written, on a throwaway environment with its own project name
and ports, never the working stack. Record the first point where reality departs
from the text. Then apply the remedy the document offers, if any, and say whether
it worked. A container's own loopback takes a different authentication path from
the bridge; a setting consumed only at initialisation does nothing for an existing
volume, so both cases are tested and the report says which.

### Tests against the code they cover

Mutation, not reading. Name the property a test asserts, make the smallest change
that violates it, and run the test. If it still passes, that is a finding, and the
mutation is always reverted.

The shapes that have appeared here: a local helper shadowing the method assertions
raise through, so they compared, differed and passed for weeks; tests asserting
the defect they existed to prevent; one half of an inherited pair covered while
the broken half was not; a test named for a number that only asserts non-empty; a
check whose subject is unreachable, so it passes forever.

## Triage

An open issue is read against merged code and recommended for closing,
duplicating, keeping, or a decision. **A textual mention is a lead, not
evidence**: verify against merged code and the original acceptance criteria, not a
similar-sounding title. Duplicates are checked by scope, since two issues with
close names routinely have different criteria and one may be a subset.

Each entry carries its evidence as URLs, commits or code paths, and states the
specific remaining gap rather than that work remains. Triage recommends; it does
not close.

## Design notes

Written when the shape is not settled, when a fix would touch many sites, or when
a choice would be expensive to reverse. No code.

**Measure before proposing.** The count changes the argument: a proposal to flip a
connection default was withdrawn once the raw-connection uses were counted and
proved to be three, all already explicit. Say how you counted and what the count
cannot see.

Then two or three shapes, each with what it costs, what it forecloses and what it
would break, including the ones you reject. Then a recommendation with the single
reason that decides it, and any constraint you would refuse to drop: if applying a
fix in a particular order would remove the only signal that a problem exists, that
is a constraint and not a preference. End with a question that can be answered by
choosing a named shape.

Where the honest answer is that a decision is a product or legal one rather than
an engineering one, the note says so instead of encoding a guess as a default.
