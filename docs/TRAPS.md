# Traps

Failures that look like findings and are not, and checks that look like checks
and are not. Each entry is a case this project actually hit, kept so the next
person recognises the shape rather than rediscovering it.

Read [PRACTICES.md](PRACTICES.md) for the discipline these cases produced, and
[GATES.md](GATES.md) for the rules that were mechanised in response.

## Test traps

The ways a test here has passed while proving nothing, or failed while meaning
nothing. Each was paid for once; none is obvious from reading the test. This
opened saying five and was still saying five several traps later, so it no
longer carries a count.

**Run it red first, and if it will not go red, say why in the body.** Every
trap below is a way a test can agree with broken code, and the cheapest check
for all of them is to run the new test against the tree without the fix. Four
tests written in one day passed against the code they were meant to prove
wrong: the revert probe on #219, because the fake's `wait_for_receipt` was an
unconfigured `Mock` and a `Mock` is not `1`; the unwind pair on #260, because
orders filled to exactly `share_amount` make `max(0, ...)` floor the second
subtraction to the same zero; the concurrency pair on #266, because both
threads were handed the same Python object and refused each other in memory
rather than in the database; and the reversal probe on #221, because a chain
balance equal to the post-deduction value made the sync a no-op. In each the
**fixture** made the broken and the fixed code agree, which is invisible in the
assertion and obvious in a red run. Where a test genuinely cannot go red —
#215's signer probe, where `consume_challenge` makes the two compared values
equal by construction, so there is no unfixed tree to run against — that is
worth knowing and worth writing in the PR body, because it means the property
is held somewhere else and the test is documentation rather than proof.

**A `Mock` that reaches a renderer never returns.** Patch a whole service class
with a bare `Mock`, let a view return its result, and DRF's JSON encoder
reaches `elif hasattr(obj, 'tolist'): return obj.tolist()` — the branch meant
for numpy arrays. Every `Mock` answers that `hasattr`, `tolist()` returns
another `Mock`, and the encoder recurses forever. The test does not fail; **it
hangs**, which in CI is a job timeout naming no test at all. Caught with
`python -X faulthandler`, whose dump ends in `mock.py` `_increment_mock_call`
under `rest_framework/utils/encoders.py`. It bites when a refactor changes
which method a view calls: the mock stops matching, starts returning `Mock`
where a dict was, and nothing says so. Give a patched service a real return
value for anything a view renders.

**`APITestCase` wraps every test in a transaction, which hides exactly the bugs
about transactions.** An orphaned row is rolled back by the harness rather than
by the code, so the test passes on the unfixed tree and proves nothing. Use
`APITransactionTestCase` for anything asserting what survives a failure. And
`shared/api/exceptions.py` turns an unhandled exception into a 500 `Response`
rather than re-raising, so `assertRaises` never fires — assert the status code
and the row count instead.

**A test of the policies proves nothing about the routing if it runs on one
connection.** `RLS_AMBIENT_ALIAS` is `default` under `settings.test_postgres`,
so a request, its fixtures and its assertions all share a connection and the
only way to take the app role is `SET ROLE`. That is a real policy test, and it
is also the shape under which a view that reached the wrong connection still
passes, because there is no other connection to reach. `settings.test_scoped`
makes `app` the ambient alias; `shared.tests.scoped.RunsOnTheScopedConnection`
carries the `databases` set, the principal a request would arrive with, and
`as_an_operator_would()`. The CI step is *Request path on the scoped
connection*. Ordinary `test` and `test_postgres` settings keep the migrate alias
for the broad unit suite. Their passing role assertions do not prove which
connection a request or task uses. CI runs the designated subset separately:

```sh
python manage.py test --settings=ledova_backend.settings.test_scoped \
  --require-scoped-coverage --noinput
```

`shared.scoped_test_runner.SCOPED_TEST_LABELS` names the required harness, route
matrix, sign-in/signup, account/document rollback, row-lock and converted-task
classes. A source inventory of classes using `RunsOnTheScopedConnection` must
match that list, so removing a class from the CI list is refused while its tests
still exist. The runner also refuses a missing or empty class, filtered subset, wrong
ambient alias, absent connection, or skipped test. Adding methods to those classes
adds them to the required run. The application role must actually lack superuser
and BYPASSRLS privileges. The locking-update tests record real `FOR UPDATE`
statements on `app` and require a successful route for every view declaring a row
lock. They assert that no test transaction is open before sending each request.
The matrix's per-case rollback supplies an outer transaction, so it cannot prove
that a view opens its own: removing a view's `atomic()` still passes that matrix
and must fail the separate locking-update test.

The confirmation task runs from an operator worker with a real principal context,
checks the database's actual role, performs its reads and writes, and must refuse
a foreign private wallet before contacting the chain. A system invocation uses
the operator connection. The test replaces provider and delivery boundaries, not
the task body or its database services. Removing `acting_for` must fail these
checks. Company operator wallets are intentionally readable under R14; they are
not suitable fixtures for a private-wallet refusal.

The scoped account-create path must provide its authenticated profile as director
on INSERT, then add membership in the same app transaction. Adding the director
only after INSERT fails the existing R19 policy, before registration can run.
After membership exists, a joint account retains its original null director.
The serializer keeps director read-only; a client cannot choose that principal.

Three fixture rules follow:

- **A bare `transaction.atomic()` in a test is exempt from
  `check-connection-binding` by design, and under `test_scoped` it binds to
  `default`** — the alias the decorator resolved at import, not the one the
  router picks. A per-case rollback written that way rolls back a connection the
  request never used, so every case after the first sees the previous one's
  rows. Tests use `shared.db.atomic()` and
  `transaction.set_rollback(True, using=current_alias())`.
- **A fixture is not a request, and it needs the connection that would really
  write it.** `snapshot()` reads the *other* tenant's rows to assert they were
  untouched; under a principal those rows are not visible at all, so it asks the
  operator. `make_eligible()` sets ID verification and a classification, which
  is a compliance action the app role may not perform on itself. Both go through
  `as_an_operator_would()`, a no-op on one connection. An operator write the
  request must then observe has to **commit**: an open transaction on one
  connection is invisible from another, so the rollback that isolates a case
  cannot also stage it.
- **A failure count far larger than the change explains is the harness, not the
  policies.** Turning the matrix scoped produced 178 failures twice, and both
  times the tell was that 159 of them shared one status code rather than the
  total. The first was the missing `set_rollback` above; the second was the same
  bare `atomic()` binding to `default`. One line took 178 to 3. Read what the
  failures have in common before reading the count.

**`SimpleTestCase` forbids a database connection, and `transaction.on_commit`
wants one even when it runs its callback immediately.** `on_commit` reaches
`get_autocommit()` and so `ensure_connection()`, which `SimpleTestCase` refuses
with `DatabaseOperationForbidden` — **on SQLite locally, not only in CI**. This
is a `SimpleTestCase` restriction rather than an environment difference; a test
that schedules an `on_commit` needs `TestCase` or `TransactionTestCase`.

**A green local run is evidence only for the tests that ran, and the set that
ran is not the set CI runs.** Two mechanisms have produced a wrong local
reading:

- `tokens.tests.test_chain_integration` needs a Hardhat node and is **skipped
  without one**. It asserts on shapes other suites share, so a change that
  passes everything locally can still break it: adding a column to the register
  export shifted every positional assertion after it, and `rows[1][8:]` in that
  suite was the one nothing local could reach. Read the register CSV by header
  name rather than by column index — `dict(zip(REGISTER_HEADERS, row))` — so a
  future column cannot break it at all.
- **A stale local environment reads as a code finding.** A `ledova-backend`
  image pinned at Django 5.2 against a `requirements.txt` asking for 6.1
  produced a wrong correction on one PR and an issue its author filed and then
  closed. Neither was advice to stop using `--parallel` — that was **a fourth
  session relaying the family into a handover**, where it told everyone reading
  it to run serially. `django/test/runner.py` on
  5.2 rejects any start method outside `{fork, spawn}` while 6.1 admits
  `forkserver`, which is Python 3.14's default on Linux — so the whole family
  of "parallel is broken here" findings is 5.2 behaviour that the pin already
  fixes. Check `django.get_version()` against `backend/requirements.txt` before
  trusting a local measurement enough to file it, and **re-run a measurement
  before repeating someone else's**: a relayed measurement is not a
  measurement.
- **Two branches verified against one scratch database read as a code finding
  too, and the count is what gives it away.** Two Django test runners racing to
  build `test_ledova` collide on `duplicate key value violates unique constraint
  "pg_type_typname_nsp_index"`, and the second one to arrive reports the damage —
  127 errors across three apps in one observed case, while the same command's
  SQLite half, sharing nothing, was green. **A failure count far larger than the
  change could plausibly cause is the signal**, and the check is one command:
  `docker ps` for another `ledova-backend` container. The fix is a PostgreSQL
  container per worktree rather than a shared one, which costs nothing and
  removes the class.
- **Images rebuilt at different times read as a code finding too, and only
  their ages show it.** A QA session rebuilt `backend` and `dashboard` from
  `main` and not `worker`, and two subscriptions wedged at paid with no shares:
  a stale worker claimed each issuance request and died before broadcasting.
  It reproduced on a second subscription with a clean history, which is what
  made it convincing. That session's own rule, worth taking verbatim: *"after
  any rebuild, `docker images | grep ledova` and check the ages match before
  believing a failure. A partial `docker compose up --build <service>` is the
  shape that produces it."*
  ([the pass-2 record](https://github.com/RonildoBraga/ledova/issues/115#issuecomment-5570522363))
  This is a different cause from the bullet above: there every image agreed
  with every other and the whole environment was simply old, so a version check
  inside one of them catches it; here each image is internally correct and they
  disagree with each other, so nothing you can read inside any single container
  is wrong and only the relative ages are evidence. What survived that
  correction is [#280](https://github.com/RonildoBraga/ledova/issues/280): a
  worker dying between claiming and broadcasting is an ordinary production
  event however it was provoked, and the recovery gap it exposed does not
  belong to whoever provoked it.

**Running a new test against the unfixed code is only half the check. Run it
against a broken expectation too.** The first asks whether the test notices when
the product is wrong; the second asks whether it notices at all. A test can pass
the first and fail the second: #221's red proof was genuine - four scalar
failures printing real numbers - while the tuple assertions beside them in the
same file could not fail, because a helper named `fail` had replaced the method
they raise through, and nobody looked. Change the expected value to something
absurd; if the test still passes, the assertion is not running. Between one
afternoon's PRs that produced five tests passing on both sides of a fix, not one
would have survived that edit.

**A test can pin a defect as an expectation, and a log-line assertion is the
easiest place for that to hide.** When the behaviour is corrected the test
fails, and the cheapest reading of that failure is *the message changed, update
the string* — a cosmetic edit that quietly retires the only record that the old
behaviour was wrong. Two in one day.
`test_pending_fresh_hashless_and_unreadable_rows_are_left_executing` asserted
the conflated message, so it recorded the conflation as the expectation.
`test_an_export_that_is_not_chain_confirmed_is_logged_as_a_warning` asserted
*"is not confirmed on chain"* and pinned an allotment fallback its own PR
deleted as wrong; it was replaced rather than reworded. Before editing an
expected string, ask what the assertion is *for*: if the answer is the
behaviour that just changed, the test is **retiring**, not failing, and the
replacement should assert the new property rather than the new wording.

React Native Testing Library 14's `render` and event helpers return promises.
Mobile test files use the workspace TypeScript project with
`@typescript-eslint/no-floating-promises` enabled. An unawaited closing press
can otherwise let an absence assertion run before the event. The real-config
control in `make check-mobile-test-awaits` removes the await from the allocation
card's closing press and requires a lint error at that line; it also checks the
unchanged test. CI runs this control alongside lint. The existing toggle test
awaits both opening and closing presses.

**A green suite can exit non-zero, and the failure text names a file that
passed.** `AssetAllocationCard.test.tsx` reported 11 files and 48 tests with no
assertion failure, and the job still failed: `ReferenceError: window is not
defined`, raised by React's scheduler committing a re-render **after** vitest
had torn the jsdom environment down. `beforeEach(cleanup)` unmounts the
*previous* test and never the **last** one, so the final render was still
mounted, with a live `useAuth` query underneath it, when the environment went
away. **Read the exit code and the test count as two separate facts**: a
suite whose assertions all pass has said nothing about what its teardown left
running.
Put `cleanup()` in `afterEach`, not `beforeEach`, and hoist any `QueryClient`
out of the render call so it can be cleared.

It is a **race**, so it is worse than a constant failure: it surfaces on
whichever commit happens to be passing through, and it resisted 49 local runs
including CPU-contended and interleaved ones. The habit that identified it in
under a minute was **comparing the trees before attributing the failure** —
`git rev-parse <sha>:dashboard` against the previous commit's, across each
affected path, turned *"probably the backend commit sitting on it"* into
*"cannot be that commit, no JS path differs"*. Do that before reading the log.

**The worst version pins an outage, and the name reads like a specification.**
`test_a_query_with_no_principal_raises_rather_than_returning_nothing` was
written during R1 and asserted that a policied query on a connection with no
principal **raises**, with a regex naming both of the two ways it can. That is
the sign-in outage, recorded as the intended behaviour, in the suite whose job
was to prove the policies. Nobody reviewing the file would have called it a
defect: it looks like a deliberate fail-closed choice, and *raises* and
*returns nothing* are both plausible readings of "fails closed" until you ask
which one an unauthenticated request needs. **A policy that denies the table is
not stricter than one that grants no rows; it is broken.** When a test's name
states an outcome, check that the outcome is the one the product wants, not
merely the one the code produces — the test was written by observing the code,
which is exactly how it came to certify the defect.

**Two independently reasonable constants, and nobody compared them.** Neither
number is wrong where it is written, and the pair is the defect. `order_write`
throttles at 30/min, which is 1,800 signing challenges an hour from one user;
the sweep that removes them ran hourly with a batch of 500. `SwapOrder.nonce`
said *"Unique nonce for replay protection"* in its `help_text` while the schema
enforced nothing, and the reconciler read `isNonceUsed` as though it did. CI
writes a generated schema to one path while the `Makefile` defaults to another
name for the same file. Each half was written by someone with a good reason and
read by someone checking that half. **When a number in one file only means what
it says because of a number in another, say so where both can see it, or derive
one from the other.**

## Measurement traps

Not a test but the same family: a reading that looks like a finding and is
actually about the observer.

**A green suite on both backends does not cover a status constraint.**
`tokens.tests.test_chain_integration` is gated on `CHAIN_TEST_RPC_URL` and skips
silently without it, and its concurrency cases are additionally
`skipUnless(POSTGRES)`. So the full SQLite suite, the full PostgreSQL suite, and
even `make chain-test` on its default settings all pass while the one suite that
drives two workers against a real chain is not running: the default reports
`20 OK (skipped=3)`, and the three it skips are the three that matter. A partial
unique index over statuses landed on that basis and CI found it —
`duplicate key value violates unique constraint` inside a background worker.

The invocation that covers it is the one CI uses:

```
POSTGRES_HOST=… POSTGRES_PORT=… POSTGRES_DB=… POSTGRES_USER=… POSTGRES_PASSWORD=… \
  make chain-test CHAIN_TEST_PORT=<free port> \
  CHAIN_TEST_SETTINGS=ledova_backend.settings.test_postgres
```

**The count does not say which cases vanished; `-v 2` does.** `skipped=3` is a
number, and a number cannot tell you that the three were the concurrency cases.
Run the suite with `-v 2` and read the names and reasons:

```
test_two_workers_on_one_increase_send_one_transaction ... skipped 'select_for_update is a no-op on SQLite'
test_a_real_deployment_bridges_a_verified_asset ...      skipped 'CHAIN_TEST_RPC_URL and the core contract addresses'
```

That turns "it passed" into "it passed without running these", which is the check
this entry exists to make possible rather than merely to warn about.

**And the reason the constraint was wrong is worth more than the invocation.** The
claim was *submit is the only entry into the in-flight set, because approval and
execution move the same row*. A partial index over statuses is entered by **every
write that moves a row into its condition**, not only by the writes that create
one — `mark_executing` moves a `FAILED` request to `EXECUTING`, which is outside
the set and then inside it. Enumerating the paths that *create* a row will not
find that; neither will pinning the state partition, which is the stronger test
and still describes rows rather than transitions. Ask instead which writes cross
the condition's boundary in either direction.

**A browser network capture includes your own probes.** `read_network_requests`
records the tab, not the application, so a `fetch` issued from `javascript_tool`
to check an endpoint is indistinguishable in that log from a request the page
made. A QA session confirmed an API's answer by hand, read the log afterwards,
and reported that the client had called the endpoint; it had not, and the author
of the fix spent time hunting a request that was never issued. Decide the
question first: to learn what the API returns, probe and do not cite the log; to
learn what the application requests, clear the capture, touch only the UI, and
read it before probing anything. An absence is the strong result here — a probe
can manufacture a request in the log but cannot manufacture zero.

**A mutation you cannot see applied is not a mutation.** A red proof works by
breaking the code and watching the test go red; if the edit silently matches
nothing, the tool exits cleanly, the suite passes, and the run is
indistinguishable from a passing suite that proves the test is worthless. Three
sessions lost time to this in one evening. One matched on JSX that Prettier had
reflowed, so the replacement found nothing and two tests were nearly written up
as red-proved without ever having been tested. One replaced a string that had
already been edited, so the "before" state was the after state. And one was not
a mutation at all but the same shape in shipped code: a glob translation whose
`**/` became `(?:.*/)?`, after which the `*` pass matched the `*` inside the
group it had just inserted and left `(?:.[^/]*/)?` — exactly one directory
level. Nothing failed. The tool succeeded twice.

**Confirm the edit landed; the pass count only tells you where to look.** What
establishes that a mutation applied is looking at the file: a diff of the
mutated tree, or the assertions below. An unchanged pass count is a clue on top
of that, not a substitute for it — a real change to load-bearing code usually
breaks something, so a count identical to the clean run is a reason to go and
check. It is only a reason. A mutation can land in a branch no test reaches and
leave the count alone honestly, and a mutation that never landed can sit beside
a count that moved for an unrelated reason. Read the number, then read the
diff.

**Assert on both sides.** Before: that the anchor exists, so a replacement
cannot silently match nothing — `assert old in text` is one line and it is the
difference between a red proof and a story about one. After: that the file
actually changed, because an anchor that exists can still be replaced with
itself. Editing by line number rather than by content trades one failure mode
for another; if you do, assert the line reads what you think it reads first.
A red proof that reports the clean count and a mutation that never landed look
identical, and they mean opposite things.

**`makemigrations --check` under the test settings cannot fail.**
`ledova_backend/settings/test.py` ends with a `MIGRATION_MODULES` mapping that
claims every app and returns `None` for each, so every app is declared
unmigrated and `makemigrations` skips all of them. The command prints **No
changes detected** whatever the models say. Measured side by side on a branch
whose model and migration genuinely disagreed:

```
default settings  ->  Migrations for 'tokens': ~ Alter field wallet
settings.test     ->  No changes detected
```

CI runs it with the **default** settings and `SECRET_KEY` and
`STORAGE_BACKEND` from the environment, which is the only form that checks
anything:

```
SECRET_KEY=x STORAGE_BACKEND=local \
  python manage.py makemigrations --check --dry-run
```

The trap is not that the test settings give a weaker answer. They give **no
answer, phrased as a passing one**, which is the same shape as a test whose
truth is guaranteed by something other than the code under test — and it is
harder to notice, because the reassuring line is what a working check also
prints. One session quoted the vacuous form in four PR bodies in one evening
before CI disagreed with it.

**A PostgreSQL-only trigger or policy is certified by the full PostgreSQL
suite or it is not certified**, and the lane's own PostgreSQL tests are not
that. `tokens/0023` added a `BEFORE INSERT OR UPDATE` trigger requiring an
owner column; its own eleven tests passed on PostgreSQL and the whole suite
passed on SQLite, and CI then found **fifteen errors in other apps' tests** —
fixtures written before the constraint existed, inserting rows the trigger now
refuses. Three of those were a real defect the SQLite suite is structurally
unable to see: a service helper accepted a call with no owner, stored `NULL`,
and left a `plpgsql` `RAISE` as the only refusal, which on SQLite is no
refusal at all. **The lane's own tests answer whether the constraint works;
only the full suite answers whose inserts it just broke.** Where a constraint
exists in the database, the Python that writes through it refuses first, so
both vendors fail the same way.
