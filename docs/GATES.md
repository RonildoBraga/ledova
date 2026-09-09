# Gates and coding rules

The rules this repository holds itself to, and the scripts that refuse a change
that breaks one. Most sections here are reached from a failing gate rather than
read forward: each names what it refuses, why, and what it deliberately does not
cover.

The method for establishing that a change is correct is in
[PRACTICES.md](PRACTICES.md). The individual failures these rules were written
against are in [TRAPS.md](TRAPS.md). How the system is put together is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## The rules

**A rule belongs here only with two things attached: the file that is its
reference implementation, and the gate that enforces it.** A rule that can get
neither is demoted to a documented exception or deleted. This is the standard
this document is being held to, and the sections above now cite a reference for
each layer; the gates are landing behind them.

The reason is stated plainly rather than hidden: most of these rules were held
by review, and a rule held by review means a green pipeline means nobody
checked. Three are gated today — the comment rule through `make
check-comments`, the "one migration per model change" half of the migrations
rule through CI's `makemigrations --check --dry-run`, and the generated design
tokens through the `git diff --exit-code` step (stated under [Clients and the
shared package](ARCHITECTURE.md#clients-and-the-shared-package)).

A new gate ships with an explicit allowlist of the offenders that exist on the
day it lands, so it is green immediately and blocks only new violations. That
allowlist is the migration backlog made visible, and CI fails if it grows. The
convergence this enables is tracked in
[issue #115](https://github.com/RonildoBraga/ledova/issues/115).

### Why the codebase diverges from these rules

The divergence is generational, not architectural, and knowing that changes
what to do about it. Every one of the 27 `XService` classes dates from the
initial seed commit; every one of the service modules added since is plain
`verb_noun` functions, and none has been added as a class. Post-seed view
modules average about 35 lines, while every view module over 140 lines is
seed-era. `tokens/services/register.py` escapes CSV cells with `shared.utils.csv_cell`;
`whitelist/views/entry.py` writes them straight from the view with no escaping
at all.

So this is a half-finished migration whose destination already exists in the
tree, not an absent standard. The consequence for how to finish it: **do not
convert the seed-era service classes in a batch.** The direction of travel is
already settled by every commit since; a sweeping rewrite would conflict with
everything in flight and buy nothing the rule below does not. New and touched
service modules are plain functions; the stateful chain clients stay classes;
the rest converts when it is next edited for another reason.

- No Django signals, with **one sanctioned receiver**. A side effect is an
  explicit call in the service (or in `perform_create`) that creates the row.
  The exception is `shared/apps.py`, which connects the `post_delete` receiver
  in `shared/storage.py` that deletes a private file once its row is gone. It is
  a receiver rather than a call because **a cascade delete never reaches a
  service**: deleting a `Company` takes its `CompanyDocument` rows and deleting
  a user takes their `Document` rows, and an explicit call in each delete path
  would leave both sets of files behind. The file delete is scheduled with
  `transaction.on_commit`, so a rolled-back delete does not destroy the file.
  `check-layers.py` flags an import of any Django signal module anywhere else
  in `backend/`, and `shared/apps.py` is an `ALLOWED` entry with a count, so
  removing the receiver fails the gate as a stale pin rather than passing
  quietly.
- No new `managers/` packages. The only `Manager` is `CustomUserManager` in
  `authentication/managers/`; everything else is a queryset wired with
  `as_manager()`.
- One `exceptions.py` per app holding only classes that are raised, with no
  `__init__` that merely forwards `detail`. Use DRF's `NotFound`,
  `PermissionDenied` and `ValidationError` for plain 404, 403 and 400. Error
  bodies carry `detail` (auth failures also `error` and `code`); clients read
  `detail`.
- Logging: `logging.getLogger(__name__)`, no prefix constants. Log errors in
  services and tasks, not requests in views. Never log an email address or a
  token: log the primary key instead, which identifies the row for an operator
  without putting a person's address in a log aggregator. On the clients, a
  `console` call takes a message and never an object -- an `AxiosError` carries
  `config.data`, the serialised request body, so logging one prints the password
  a failed sign-in was sent with. `describeFailure` in `packages/shared` turns
  any thrown value into the narrow line worth keeping: status, error code, and
  the method and path with the query string cut off.
  [The logging privacy gate](#the-logging-privacy-gate) below is the mechanical
  half of this rule.
- Constants: `TextChoices` next to the model, numeric thresholds as module
  constants in the app's `constants.py`.
- **No comments and no docstrings in source.** Names and tests carry the
  meaning. There is no "unless it is really needed" clause: wanting to explain a
  line is the signal to rename the thing or add a test, never a licence to
  comment it. `make check-comments` enforces this, and
  [the gate](#the-comment-gate) below is the authority on what it covers — it
  lists the trees once, and a test holds that list to the one the gate reads, so
  this paragraph does not carry a second copy to go stale. The root `scripts/`
  tree is outside them: every file there carries a module docstring. The only comment
  lines permitted are functional directives the tooling reads: `# noqa`,
  `# type:`, `# pragma`, `# fmt:`, `# isort` and the shebang/coding lines in
  Python; `eslint-disable`/`eslint-enable`, `@ts-ignore`/`@ts-expect-error`/
  `@ts-nocheck`, `prettier-ignore`, `/// <reference`,
  `@vitest-environment`/`@jest-environment`, `istanbul`/`c8`/`v8` coverage
  pragmas, `/* global */` and `biome-ignore` in TypeScript and JavaScript; and
  `// SPDX-License-Identifier` in Solidity. That list is closed: a directive not
  on it is a comment, however useful it looks. No section banners, no
  Args/Returns blocks, no `help_text` that restates a field name, and no note
  explaining a swallowed error — `no-empty` carries `allowEmptyCatch: true` in
  the dashboard, mobile and `packages/shared` ESLint configs precisely so an
  ignored `catch` can stay empty. Configuration and documentation files
  (`.env.example`, YAML, Makefiles, Dockerfiles, Markdown) are documentation and
  keep their comments.
- Tests: `APITestCase` under `<app>/tests/`, superusers via `create_superuser`.
  `make test` runs on SQLite; CI also runs the migration-stage tests and the
  whole suite on PostgreSQL.
- Client tests: every JavaScript workspace has a runner and CI runs all of them
  through `make test`. `packages/shared` and `mobile/` use Jest, the dashboard
  uses Vitest, `contracts/` uses Hardhat. Mobile's config is `mobile/jest.config.js`
  (the `jest-expo` preset); its tests sit beside the code they cover as
  `*.test.ts`/`*.test.tsx`, the same convention the dashboard follows, so the
  comment gate reaches them and they carry no comments either.
  `mobile/src/hooks/useFeatureFlags.test.tsx` is the reference: it mounts the
  hook with `renderHook` from `@testing-library/react-native` — asynchronous
  since version 14, so it must be awaited — over a `QueryClientProvider`, and
  mocks `../services/apiClient` rather than the `@ledova/shared` service that
  calls it. A test must leave no promise pending when it ends: a request stubbed
  with a promise that never settles keeps Jest alive after the run reports
  success, so stub with a deferred you resolve before the test returns.
- Linting is a gate, not a local habit. `make lint` runs ESLint over the
  dashboard, `packages/shared`, marketing and mobile, and solhint over the
  contracts, and CI runs it on every pull request. Warnings are allowed and
  errors are not: every workspace is at zero errors, so the gate holds that line
  rather than trying to reach it. It exists because a Dependabot bump of ESLint 9
  to 10 passed all four checks — nothing in CI ran ESLint at all — while
  `eslint-plugin-react` 7.37.5, its latest release, crashed on the first file
  with `contextOrFilename.getFilename is not a function`. A tool nothing runs is
  a preference, not a standard.
- The dashboard smoke: `dashboard/tests/smoke/*.smoke.ts` drives a real Chromium
  against the built bundle, and `make smoke` runs it in CI on every pull request.
  It answers one question — does the shipped bundle boot and route without
  throwing — so it stubs `**/api/**` with a 401 instead of expecting a backend.
  The console-error assertion filters exactly the noise that stub provokes and
  nothing else, which is what keeps it able to fail: an uncaught exception from
  the bundle still ends up in the same list. A smoke test never depends on the
  API, the database or the chain; anything that does belongs in the Django suite
  or `make chain-test`.
- Migrations: one per model change, never edit an applied one. On testnet an
  unapplied one may be deleted.
- Dependencies: nothing in `requirements.txt` or a `package.json` without an
  importer.
- Endpoints: nothing routed without a caller in `dashboard/`, `mobile/`,
  `packages/`, a documented external consumer, or the operator API. Check
  `packages/shared` before concluding a route is dead: `POST
  /api/wallets/batch-check-balances/` looks unreferenced from either app but is
  called through `packages/shared/src/services/wallet-balances.ts`, which the
  dashboard's add-wallet modal and the mobile balance hook both use.
- The operator API is the named exception: `IsAdminUser`-gated routes an
  operator drives from a script or a client the repository does not ship. The
  whole `/api/v1/whitelist/` tree (`whitelist/urls.py`) and
  `/api/portfolios/{uuid}/add-wallet/` and `/remove-wallet/` are in it. They
  have no caller in either app and are kept, tested and documented deliberately.
- The dashboard, the mobile app and `packages/shared` are first-class clients:
  every response key, status code and URL they read is a contract the backend
  keeps.

[CONTRIBUTING.md](../CONTRIBUTING.md#gates) lists the commands that gate a pull
request, and which of them CI does not run for you.

## The comment gate

`scripts/check-comments.py` is the mechanical half of the no-comments rule.
`make check-comments` runs it, `make check` includes it, and CI runs it as its
own job. It needs no dependencies and no installed environment: Python 3 and a
checkout are enough.

It parses rather than greps. A `//` inside a URL string, a regex literal like
`/^[mM]\//`, and a URL or an apostrophe in JSX text are not comments, while a
`/* ... */` inside a `${...}` substitution or a `{...}` JSX expression is one.
`.tsx` and `.jsx` are scanned with a JSX mode, so a closing tag does not hide
the rest of its line. Python goes through `tokenize` for comments and `ast` for
docstrings, which also catches a bare string statement sitting where a docstring
would.

What it covers, by extension: `.py` and `.css` under `backend/`; `.ts`, `.tsx`,
`.js`, `.jsx`, `.mjs` and `.cjs` in the client, shared, mobile-script and
contract-script trees, plus `.css` in `dashboard/src` and `marketing/src`;
`.sol` under `contracts/contracts`; `.py` in `mobile/scripts`; and `.m`/`.mm`
native templates in `mobile/plugins`. Native preprocessor directives are code;
ordinary native line/block comments are refused. The build configuration at the root of
`dashboard/`, `marketing/`, `mobile/` and `contracts/` is covered too, but only
at that root, not recursively.

The trees are, in full: `backend`, `dashboard/src`, `mobile/src`,
`mobile/scripts`, `mobile/native-tests`, `mobile/plugins`, `mobile`, `packages/shared`, `packages/scripts`,
`marketing/src`, `dashboard`, `marketing`, `contracts`, `contracts/contracts`,
`contracts/scripts`, `contracts/test`.

`TREES` at the top of the script is the machine-readable copy of that sentence,
and `scripts/tests/test_check_comments_trees.py` fails if the two disagree in
either direction. That test exists because they did disagree: #185 added
`mobile/scripts` to `TREES` and this section kept saying otherwise, and the
instruction to "change it and this section together" is not a mechanism.

One thing sits outside it: the admin templates under `backend/*/templates/` are
not checked. They carry no comments today; keep it that way.

A green CI run is evidence for the trees in `TREES` and nothing else.

Both of this repository's hand-maintained gate lists are now checked in **both**
directions. A list that only refuses removals still lets a new thing go ungated,
and the symptom is the same in both cases: a green line reporting a number that
looks like coverage and is a numerator.

`check-comments.py` states what is deliberately **not** scanned in `NOT_SCANNED`,
each entry with a reason, and fails on any source file no tree reaches. Without
it the extension tuples and the recurse flags were prose — flipping `backend` to
`False` drops 838 files and the gate still passes.

`check-type-check.py` discovers any directory carrying both a `package.json` and a
`tsconfig.json` and fails if it is neither in `WORKSPACES` nor in `NOT_A_WORKSPACE`
with a reason. A fifth workspace nobody added is now a failure rather than a
silence.

## The type-check gate

`scripts/check-type-check.py` answers one question: would a workspace's
`type-check` script examine any files at all? `make check-type-check` runs it and
CI runs it beside the other source gates.

The dashboard and marketing both use a solution-style `tsconfig.json` — `"files":
[]` plus `references` — and both ran `tsc --noEmit`, which **does not follow
project references**. Against that config it type-checks nothing and exits 0. A
deliberate `const x: number = "not a number"` passed `npm run type-check -w
dashboard` and passed the root `npm run typecheck`, which is what CI's
*Type-check workspaces* step runs. Both now use `tsc -b --noEmit`, which does
follow them.

Type errors were still being caught, by `make build`'s `tsc -b` earlier in the
same job — so this was not errors reaching `main`, it was a check that had
stopped being one while reading as green. That is the more dangerous state,
because the safety depended on an unrelated step running first: reorder the job,
split the type-check out, or drop the build and the errors ship.

The gate is static and cheap: a workspace whose tsconfig examines no files of
its own must type-check in build mode. It does not run `tsc`.

What counts as examining no files is decided by TypeScript, not by the presence
of one key, so the rule was calibrated against the compiler rather than against
the documentation. Each shape below was measured by type-checking a file with a
known error under it:

| tsconfig | `tsc --noEmit` |
| --- | --- |
| `{"files": []}` | examines nothing |
| `{"files": [], "include": []}` | examines nothing |
| `{"include": []}` | examines nothing |
| `{"references": [...]}` | examines everything |
| `{"files": [], "include": ["**/*"]}` | examines everything |
| `{"extends": <base with "files": []>}` | examines nothing |

The last row is why `extends` is resolved rather than read past. `tsc
--showConfig` does not print the inherited `files`, but the inheritance is real:
a workspace whose base carries the empty `files` is exactly as unchecked as one
carrying it directly. The chain is consulted only when the local config does not
already settle the question, which is why `mobile` — whose base is `expo/tsconfig.base`
— needs no install to be judged: its own non-empty `include` is enough.

`files` and `include` resolve **independently** down the chain, each taken from
the last config that declares it. A config extending `["<include: src>",
"<files: []>"]` type-checks `src` in either order, so the two cannot be carried
as a pair.

What the gate is for is narrower than "examines no files": it is *examines no
files **and reports success***. A config whose `exclude` cancels its `include`
examines nothing too, but tsc refuses it loudly — `error TS18003: No inputs were
found` — and exits 2, so CI already catches it. The shape worth a gate is the one
that exits 0 while checking nothing. Measured:

    {"include": ["src"], "exclude": ["src"]}   exit 2
    {"files": [], "references": [...]}         exit 0

Two things the gate refuses to do quietly. An `extends` it cannot follow is
reported, not skipped — a gate answering "nothing found" because it could not
read the file is the failure this rule exists to prevent, one level up. And
`tsconfig.json` is JSONC, so block comments and trailing commas are stripped
before parsing; a file it still cannot parse is named in a message rather than
raised as a stack trace, because "the gate crashed" and "the gate found
something" must not look the same in CI.

A tsconfig that examines nothing and references no project is reported too, with
different advice: build mode would not help it, so it is told to state a file
set.

## The layer gate

`scripts/check-layers.py` is the mechanical half of the "Never contains" column
of the layer table under [Backend layers](ARCHITECTURE.md#backend-layers).
`make check-layers` runs it, `make check` includes it, and CI runs it in the
same job as the comment gate. Like that gate it needs only
Python 3 and a checkout. `backend/shared/tests/test_layer_gate.py` pins each
rule against a snippet, so the decisions below are executable rather than prose.

`LEGACY` maps `file:rule` to a **count**, not to a bare key, and that difference
is the gate. `ALLOWED` sits beside it for the opposite kind of entry: a finding
that is correct and permanent rather than owed. It carries a reason and a count —
a reason so nobody has to rediscover why, and a count because an exception that
excused a whole file would reopen the hole `LEGACY`'s counts close. Today it holds
one: `CompanyViewSet.get_queryset` returning `Company.objects.all()` for the
administrative actions, which #119 already pins from the route side. Keeping it out
of `LEGACY` is what lets `LEGACY` reach zero and mean it. Keyed per file, an already-excused file could gain any number of new
violations while only an informational total moved; the run stayed green. Now a
count that rises fails, a count that falls fails as stale, and the message names
both numbers. `python3 scripts/check-layers.py --show-legacy` prints the entries
with line numbers. Move the logic rather than raising a count: they only fall.

The rules judge each `.objects` expression rather than the function around it. A
scoping call counts when it is *in that expression* — in the chain, in its
arguments, carried on a local that the expression filters by, or carried on the
queryset the expression is built from. A scoping call mentioned elsewhere in the
same function does not, because that is how `if staff: return Thing.objects.all()`
sat unseen beside a scoped branch, which is the shape #127 had to fix by hand.

Two calibrations are worth stating, because both times the gate was wrong and
both times the tell was the same — one shape appearing in several files at once.

- **`transaction.atomic` in a view.** `@transaction.atomic` decorating `create`,
  `update`, `partial_update` or `destroy` says *this whole generic operation is
  atomic*, and the row lock belongs in `get_queryset` where DRF fetches it. That
  is allowed. `with transaction.atomic():` in a body, or the decorator on a
  `perform_*` hook, says *I am orchestrating*, and orchestration is the
  definition of a service. That is flagged. The distinction is syntactic and
  sharp, and sharpening it caught more real workflows, not fewer.
- **A query in a model.** The rule is *queries on other models*, so the gate
  compares the receiver: `cls.objects`, `self.objects` and the model's own class
  name are its own manager and are allowed, which is what makes a lazy singleton
  accessor like `Operator.get()` or `Country.get_or_create_for_code()` legal
  where it stands. Any other model's manager is flagged, whether it sits in a
  transition, a derived property or a `@classmethod` finder, and belongs in a
  queryset or a service.

The general form: when a rule flags the reference app, or the same shape in
several files at once, the rule is wrong and the fix is to sharpen it. Never
excuse a file into `LEGACY` to make a number go down.

The heuristic has a boundary, found by trying to apply it a third time and being
argued out of it. Sharpening the rules surfaced eight findings, four of them one
shape in four files — `thing = self.get_object()` and then
`SecondModel.objects.for_thing(thing)`. I read four files agreeing as the rule
being wrong and loosened it to follow the row. That was a misreading: **the
heuristic is about false positives, and four files agreeing means the shape is
common, not that it is safe.**

Whether a row the caller can see implies its children are visible is a property of
each relation, and no rule over the syntax can know it. This product has a
relation where it is meant not to hold — `offerings/views/offering.py`'s
`subscriptions` action is outside `MANAGE_ACTIONS`, so it reads through
`visible_to_user`, and `Subscription.objects.for_issuer(offering)` would return
every investor's subscriptions. It is correct today only because
`Company.visible_to_user` and `Company.manageable_by_user` have identical bodies,
and the [tenancy model](ARCHITECTURE.md#tenancy-model) describes deliberate
pressure to widen the first.
Loosening the rule would have removed the standing warning from the one line that
says so. Those four are pinned with counts instead.

The `bare-admin-view` rule is the one rule outside that table's "Never
contains" column, and it needed the walker widened before it could exist:
`layer_of` recognised `views`, `models` and `tasks`, so **no admin module was
parsed at all** — 136 files scanned became 190. Adding the layer on its own
found nothing, because no other rule applies to `admin`, which is what let the
rule land with an empty `LEGACY`.

It flags any `admin_view` attribute in the `admin` layer. The two helpers are
excluded structurally rather than by name: `shared/utils/` is not a layer, so
`layer_of` returns `None` for it and the walker never opens it. That is a load-
bearing coincidence, so `test_layer_gate.py` asserts it rather than trusting it.
A genuinely row-less admin page — an operator dashboard, say — is a legitimate
bare `admin_view` and takes an `ALLOWED` entry with its reason, not a `LEGACY`
one: it is correct and permanent rather than owed. There are none today.

The rule reads syntax, so `getattr(self.admin_site, "admin_view")` goes past it.
That is the same necessary-not-sufficient boundary stated above, and
`test_admin_row_actions.py` closes it from the other side: it walks the live
URLconf and fails when any custom admin route is served by a callback from
outside the two `shared.utils` helpers, whatever syntax registered it.

The `django-signals` rule is the second rule outside that column, and it needed
a second walk rather than a wider one. The four-layer walker opens 191 files;
signals can be connected from any of them and from `apps.py`, which is in no
layer at all, so the rule walks every `backend/**/*.py` outside `migrations/`
and `tests/` — 522 files. It flags all three import shapes,
`from django.db.models.signals import ...`, `import django.db.models.signals`
and `from django.db.models import signals`, aliased or not.

`backend/shared/apps.py` is an `ALLOWED` entry rather than a name the walker
skips, and the difference matters in the direction people forget: an `ALLOWED`
entry carries a count, so **deleting the receiver fails the gate as a stale
pin**. A skipped path would have gone quiet instead, and the rule exists to keep
the one receiver visible as much as to keep others out.

**Its scope is every Django signal family, not just the model one**, which is
the second boundary this rule needs stated. It first shipped matching
`django.db.models.signals` alone, and `from django.dispatch import Signal` --
the purest instance of what the rule forbids, since that is how a *custom*
signal is defined -- passed, as did `django.contrib.auth.signals`, the family
most likely to appear under `authentication/`. It now matches `django.dispatch`
and anything beneath it, and any `django.*` module with a `signals` segment, in
both the `from X import y` and `import X` forms, aliased or not. The first asks
about the **joined** module path, so `from django import dispatch` is the same
import as `import django.dispatch` and is caught as one. A `signals` module
outside `django` is somebody else's and is not this rule's business. Like
`bare-admin-view` it reads syntax, so
`importlib.import_module("django.dispatch")` goes past it.

### The seed-era service classes

The 27 `XService` classes from the initial seed commit are the accepted exception
to "a service is a module of plain functions". They are not backlog and not a
LEGACY entry: no gate flags them, converting them in a batch would conflict with
everything in flight, and every service written since is already plain functions.
They convert when one is next edited for another reason. Recorded here so the
absence of a gate for them reads as a decision rather than an oversight.

## The connection-binding gate

**A transaction and its queries must use the same connection.** Use
`shared.db.atomic` and `shared.db.on_commit`; their implementation is
`backend/shared/db/transactions.py`. Unless an explicit `using` is supplied,
`atomic` resolves `current_alias()` at `__enter__`, including each invocation of
a decorated function, and `on_commit` resolves it on each callback-registration
call. A transaction on `default` cannot roll back writes the router sends to
another alias. `django.db.connection` also always reaches `default`, whose R1
role bypasses row-level security, so a raw cursor through that proxy can bypass
the caller's scope. Raw access names its connection with `connections[alias]`,
usually `connections[current_alias()]`. This is the R23 rule; the role model is
in [Tenancy model](ARCHITECTURE.md#tenancy-model).

`scripts/check-connection-binding.py` is its static gate.
`make check-connection-binding` runs it, `make check` includes it, and CI runs it
alongside the other source gates. Python 3 and a checkout are enough. It parses
every `.py` file under `backend/`, excluding any path containing `tests`,
`migrations`, `__pycache__`, `.git` or `node_modules` as a path component.

It refuses the literal attribute paths `transaction.atomic`,
`transaction.on_commit` and `connection.cursor`, both as calls and as attribute
references. That includes a bare `@transaction.atomic` decorator or an assignment
that saves the method for later. Naming `using` explicitly on
`transaction.atomic` does not exempt it: application code uses the shared helper.

The import check refuses these forms even before a call appears:

- `from django.db import transaction` and `from django.db import connection`.
- Any `from django.db.transaction import ...`, including direct imports of
  `atomic` and `on_commit`.
- `import django.db.transaction`, or a module name beginning with that path.

Each form is recognised with or without an `as` alias, because the check reads
the imported name. `from django.db import connections` and imports from
`shared.db` are allowed.

`ALLOWED` exempts three whole files: `backend/shared/db/transactions.py`
implements the helpers; `backend/shared/db/principal.py` binds its local
`connection` through `connections[alias or current_alias()]`; and
`backend/shared/management/commands/check_rls_roles.py` deliberately asks each
alias by name. The gate fails if an allowed file disappears.
`scripts/tests/test_check_connection_binding.py` also requires every allowance
to state a reason and still produce a finding without its exemption.

**It reads syntax, not resolved symbols or runtime routing.** It does not follow
re-exports, assignments, dynamic imports or `getattr`. For example,
`import django.db` followed by `django.db.transaction.atomic()` is not recognised.
The refused imports above catch aliases of those imports; there is no general
alias analysis. Code outside the scanned files and code inside an allowed file
are unchecked, and choosing `connections[alias]` is not proof that the alias is
the right one. The gate cannot establish which role a live connection uses or
whether a transaction really rolls back its queries; the scoped-connection tests
described in [Test traps](TRAPS.md#test-traps) exercise that boundary.

## The schema response gate

`scripts/check-schema-responses.py` fails when a view returns a shape the
generated OpenAPI schema does not know about. `make check-schema-responses` runs
it and CI runs it beside the other source gates. It is static and needs no
database: it reads the view source, not a generated schema.

drf-spectacular infers an operation's response from `get_serializer_class()`. A
view that builds its own `Response` with a different serializer is documented as
returning the wrong shape, and every consumer that trusts the schema inherits the
error - including the API type drift gate, which cannot tell a schema defect from
a type defect and would record the former as the latter.

**A routed function view that does not return a DRF `Response` is outside both
of this gate's rules**, and outside drf-spectacular's generator as well, so it is
absent from the schema and nothing records that as deliberate. The fix for one is
to bring it inside, not to note it.

There is one today: `GET /api/v1/trading/events/stream/`, a plain async Django
view returning `StreamingHttpResponse` over a Redis subscription. `hand-built-
response` declines it because there is no `Response`, `undeclared-action` because
there is no `@action`, and the generator declines it because it is not a DRF
view — `@extend_schema` on it changes nothing, measured. A path missing from the
schema also cannot be diffed by the API type drift gate, so a shared type
describing the stream would be invisible to both.

It is documented by a `POSTPROCESSING_HOOKS` entry that injects the path,
`shared/api/schema_hooks.py`. The event names in it are **derived from
`tokens.events.TRADING_EVENT_TYPES`** rather than listed, so the documented
contract cannot drift from what the publisher may send, and
`shared/tests/test_schema_documents_the_stream.py` fails if the hook is
unregistered, if the list is hand-written, or if the route is renamed. A second
such route should take the same shape rather than a second exemption.

`POST /api/v1/tokens/` was the clearest case. `get_serializer_class` returns
`ShareTokenCreateSerializer` for the `create` action, so the schema said the 201
body had eight write fields and no `uuid` or `status`, while the view returned
`ShareTokenDetailSerializer(token).data`. The TypeScript was right and the schema
was wrong, and the drift gate reported it as a type error.

Two rules:

- **hand-built-response** - a routable method that returns
  `Response(XSerializer(...).data)`, directly or through a private helper, must
  carry an `@extend_schema` naming what it returns. `Response(serializer.data)`
  where `serializer` came from `self.get_serializer(...)` is exactly what the
  generator already infers, so it is not a finding.
- **undeclared-action** - an action returning a literal dict body must declare it
  too, since the generator has no serializer to read. Error paths are excluded:
  a `Response({...}, status=HTTP_4xx)` is not the contract.

Naming a response is enough; the gate does not verify the declaration is
accurate, because that is not decidable from syntax. What it decides is that
somebody stated something, which is the difference between a wrong answer and no
answer. `@extend_schema(exclude=True)` is also an answer, and is the right one
for a provider-facing webhook - it makes "deliberately absent" and "the generator
could not see it" stop looking the same.

A private helper serves no route, so what it returns is attributed to the
routable methods that call it. `SubscriptionViewSet._detail` is why: it returns
`SubscriptionDetailSerializer`, and the actions that matter are `submit` and
`withdraw`, one of which the generator documented as returning
`SubscriptionWithdrawSerializer`.

`LEGACY` carries the literal-body actions that predate the gate, keyed by
`file:rule` and valued by a count that may only shrink.

## The test shadowing gate

`scripts/check-test-shadowing.py` fails when a test class defines a method whose
name is a `unittest.TestCase` attribute. `make check-test-shadowing` runs it and
CI runs it beside the other source gates. It is static and needs no database.

**Why it is worth a gate rather than a convention.** Most of the assertion
surface raises through `TestCase.fail`. Only the few that call
`raise self.failureException` themselves survive a shadowed one: `assertEqual`
on a **scalar**, because `_baseAssertEqual` raises directly, plus `assertTrue`
and `assertRegex`. A test class that defines `def fail(self, tx_hash)` as a
helper **replaces the method everything else raises through**, so those
assertions build their difference message, call the helper, and pass.

**The enumeration is deliberately not written here.** Three sessions measured
which assertions go silent and produced three different lists, each describing
the methods that session happened to try. The list is a snapshot of one CPython
release and of one person's sample; the rule is not. `scripts/tests/` pins the
behaviour instead, because a test goes red when it rots and a paragraph does
not - which is the failure this whole section is about.

What is stable is the shape: a mixture, and that is what makes the shadowing
invisible. The suite keeps failing where you are looking and stops checking
where you are not.

That is not hypothetical. `ReversingOnlyWhatWasDeductedTest` shipped with a
`fail(tx_hash)` helper, and six tuple assertions across that file were inert
from the day they merged. They were found only because a deliberately reverted
fix did not turn them red - see [TRAPS.md](TRAPS.md), **Test traps**, "run it red first".

The rule exempts the documented override hooks - `setUp`, `tearDown`, their
class forms, `setUpTestData` and the runner protocol - because those exist to be
overridden. Everything else on `TestCase` is refused, and the reserved set is
**derived from `dir(unittest.TestCase)` rather than listed**, so a name the
standard library adds later is covered on the day it is added.
## The API type drift gate

`scripts/check-api-types.py` fails when a shared TypeScript type declares a field
**required** that the endpoint it is used for never sends. CI runs it in the
Django job, because it reads a schema generated by drf-spectacular and generating
one touches the database.

One direction only. A field an endpoint sends that no type models is dead weight:
TypeScript never surfaces it, so nothing reads it and nothing breaks. A field a
type declares required that the endpoint never sends is different in kind - every
read of it type-checks and every read of it is `undefined` at run time, and no
care at the call site can catch that, because the type is the thing being trusted.

Trading SSE event names are checked in both directions. The gate resolves
`TRADING_ENDPOINTS.EVENTS.STREAM` and compares its generated `x-sse-events` with
the shared `TradingEventType` union, which keys the invalidation map. The schema
marks the connection-only event separately through `x-sse-connection-event`,
derived from the server's `CONNECTED_EVENT`; that event has no invalidation
listener. Missing metadata, an uninspectable union, a server-only event or a
client-only event fails the same CI gate. These names have no debt allowlist.

**Matching goes through `paths`, never through names.** drf-spectacular names its
components after serializer classes, so a component and an interface can share a
word and describe unrelated endpoints: this repository has `documents.Document`
and `companies.CompanyDocument` side by side, both with upload endpoints. A
name-matching version of this gate reported a bug that did not exist (#207,
closed as invalid) on exactly that collision. So the gate resolves each
`constants/api.ts` template to a URL shape, finds each service call in
`packages/shared/src/services`, matches it to the operation the schema declares
at that path and verb, and compares the type argument against **that operation's
2xx response schema**. The test suite pins the collision case.

Every HTTP call in a shared service must pass a resolvable endpoint constant,
including wallet transfer helpers and calls with no response type argument.
Literal URLs, computed URL parameters, unresolved constants and uninspectable
response types fail the gate;
there is no unchecked-call allowlist. Nested interface members stay under their
object rather than becoming required root fields. Response unions are expanded
so the EVM and Bitcoin preparation types are checked against their respective
response shapes. The wallet action schema describes the actual challenge,
verification, sync, preparation, broadcast and batch-balance replies.

Asset and holding responses carry `valueSource`: `market`, `nav`, `par` or
`unpriced`. The price writer records provenance atomically with the USD quote.
Holding values and wallet totals use the same positive USD quote with known
provenance; raw legacy prices are retained but are not valuations. NAV updates
and the configured AUDY par producer both use this writer.

Allocation items keep `source` beside `basis`: source describes the valuation,
while basis describes the percentage denominator. Both clients label the list
and chart; mobile arc selection reveals the source and can be tapped again to
restore the total. An entirely unpriced portfolio still draws quantity shares.
Partial or conflicting cross-wallet valuations retain known amounts but mark
the aggregate unpriced instead of inventing one source; the chart identifies
an incomplete valuation and the list preserves its unpriced percentage dash.

Wallet `signingPreference` is a self-declared client preference (`hardware`,
`software` or null), not custody evidence. It chooses a signing interface and
may be changed without changing the address verification status. Key
fingerprints, public keys and derivation paths are also client-provided data;
the presence of that metadata does not identify the signing device. New
wallets with no preference remain unspecified instead of claiming hardware.
The legacy `walletType` API name remains an alias for compatibility; conflicting
values in the two names are rejected. Current clients use `signingPreference`.
The stored field is renamed without deleting existing preferences or wallets.

A valid verification signature proves control of the address for that challenge;
a hardware device and software can produce the same signature. `VERIFIED` has
no hardware-custody meaning, and no server permission or compliance rule uses
the signing preference. The existing administrative verification override is
not a device attestation either. Both wallet detail views label the preference
as self-declared and keep address verification separate.

Wallet holdings are an array and identify their wallet with `walletUuid`. Asset
snapshots do not supply calculated chart changes; clients derive those from
prices. Transactions expose `createdAt` but do not promise `updatedAt`. Sync
responses contain `syncResult`, rather than an asynchronous task identifier.
The outcome-reporting behavior remains tracked by #237.

Field names are compared with separators removed and case folded, because the
wire is camelCase - `djangorestframework-camel-case` renders it - while a schema
component may carry either form. `address_line_1` and `addressLine1` are one
field and must not read as two.

Two lists carry what predates the gate, and they are **separate on purpose**:

- `TYPE_DEBT` - the type promises what the API does not send. This is what the
  gate exists to catch.
- `SCHEMA_DEBT` - the reverse: the TypeScript is correct and the *schema* is
  wrong, because a view builds its own `Response` with a serializer other than
  the one `get_serializer_class` names, and the generator documents the latter.

Recording the second as the first would assert something false about correct
code, and an allowlist that asserts something false is worse than no allowlist,
because the next reader trusts it. #211 empties `SCHEMA_DEBT`; when it does, the
counts here fail as too high, which is the intended way to find out.

Both are count-keyed and both may only shrink: a number higher than what is there
fails as loudly as a number lower, so neither list can quietly outlive the problem
it records. Every entry states a reason naming the serializer or view responsible,
per the rule that an exemption must name a mechanism rather than assert a property.

## The error body gate

`scripts/check-error-bodies.py` fails when an API error response would carry a
caught exception's own text. CI runs it beside the other source gates; it is
static and needs no database.

An `APIException` subclass raised with an argument is served to the caller as the
response body by `shared/api/exceptions.py`. When that argument is built from a
caught exception, the body is whatever the underlying library chose to say — and
for a `requests` failure that is the request URL, which in this deployment
carries the node provider's API key as a path segment. Measured on `main` in
#243, through the real handler:

```
STATUS 500
BODY   {'detail': 'Transfer preparation failed: Max retries exceeded with url:
        https://base-sepolia.g.alchemy.com/v2/<the key>'}
```

The rule is the one the logging gate already applies, one layer out. That gate
refuses handing a whole provider response body to a **log** formatter, because a
whole body is whatever the provider chose to send. A response body reaches a
caller rather than an operator, so the same reasoning applies with more force.

Inside an `except ... as name:` handler, an `APIException` subclass may not be
constructed from `name` — not the bare name, not `str(name)`, not an f-string
interpolating it, not through a local assigned from any of those, and not as a
keyword argument. Every subclass carries a `default_detail`, and the fix is a
fixed message plus a logged diagnostic:

```python
        except Exception as e:
            logger.error(f"Preparation failed: {e}")
            raise TransferPreparationException("Transfer preparation failed.") from e
```

Nothing a caller can act on is lost. The reasons that matter to a caller are
separate exceptions raised **above** the generic branch — `NotWhitelistedException`,
`InsufficientBalanceException`, `TokenPausedException` — and they keep their
messages. What is lost is the part that was never for the caller.

Two things are deliberately not findings. A message built from the repository's
own state — `f"Cannot execute request with status '{request.get_status_display()}'"`
— names a condition rather than repeating a library, so it stays. And
`shared/utils/blockchain.decode_exception_to_message` is a **sanitiser**: it
reads structured revert data, explicit revert text and preserved exception causes,
decodes a known reason and returns a constructed sentence or a stated default.
URL hex, unknown selectors and conflicting reasons produce no diagnostic echo.
The traversal and payload sizes are bounded, and incomplete allowance/balance
data does not invent zero amounts. Decoded ABI integers are explicitly base
units because the generic decoder does not know the token's decimals. Token
and ERC-20 transfer preparation use it after a refused gas estimate; the
ERC-20 wrapper's sanitized outer message retains its underlying cause. Native
preparation and Bitcoin paths do not produce ABI revert data, and the existing
broadcast defaults still cover transport and node-submission failures. It is named in `SANITISERS`, and adding a
name there is a claim about that function which has to be true.

**The same rule one layer out: a field a client-facing serializer exposes.** An
`APIException` is not the only way an exception's text reaches a caller. A model
field assigned inside a handler and served later by a serializer carries it in a
**200 body**, where the first rule cannot see it. #366 found
`review_notes = f"Execution failed: {str(exc)}"` on a share issuance request and a
capital increase, both exposed by the issuer's own serializers.
Those serializers now omit internal reviewer text, including ambiguous legacy
notes. The separate `execution_notes` field carries the safe execution messages.

The gate's second rule refuses handing a caught exception's text to a model method
that writes such a field. Both halves of it are derived from the source rather than
listed:

- **which fields a client reads**, from each serializer's `Meta.model` and
  `Meta.fields` together — matched by model, so `SwapOrder.error_message` counts and
  `MintRequest.error_message` does not, because `MintRequest` has no serializer at all
- **which methods write them**, including fields and writers inherited from base
  models, local aliases of their parameters, and calls through model helpers such
  as `mark_failed` forwarding its message to `_save_attempt`

**What it cannot decide is the receiver.** `ReviewableRequest.mark_failed` writes
`execution_notes`, which two client serializers expose; `ShareIssuance`,
`BlockchainTransaction` and `MintRequest` each have a `mark_failed` that writes
`error_message`, which no serializer of theirs exposes. A call site gives the method
name and not the model, so `ALLOWED_NOTE_RECEIVERS` names the receiver expressions
that are the operator-facing ones. Each entry is a claim about that receiver, in the
way `SANITISERS` is a claim about a function, and the claim has to be true. A
sanitiser protects only the expression passed through it: a decoded fragment
beside raw exception text in the same argument is still a finding.

**Taint outlives the handler.** Python unbinds `as name` at handler exit, so the
shape that escapes is a local assigned from it and used afterwards:

```python
        except Exception as exc:
            failure = exc
    if failure is not None:
        request.mark_failed(str(failure))          # outside the handler
```

That is the capital-increase half of #366, and a handler-only scan does not see it —
measured, because the first version of this rule did not. The scan taints names
assigned from the caught exception and then reads the **enclosing function**, so a
finding one statement later is still a finding.

**An exception handed to a helper that builds one.** #390 measured the third way
past both rules, and it is the one that has already nearly cost something: a
rebase on #339 restored `f"{label} failed: {error}"` inside
`whitelist/services/whitelist.py:_refuse`, and the gate exited 0 while one test
caught it. Neither end is visible — at the call site the callee is
`self._refuse`, not a subclass; inside the helper there is no handler for the
taint to start from.

The set is derived from the source too, and **it records which parameters reach
the construction, not merely that some parameter does.** That distinction is the
whole rule. `_refuse` builds its exception from `tx_type`, a safe enum, and logs
`error` — so "does this function build an exception from a parameter" is true of
it *either way*, and a rule asking only that fires on the correct file as loudly
as on the broken one. The first version of this rule did exactly that, and
produced identical output with and without the defect:

```
with the fixed message      exit 1, three findings
with the leak restored      exit 1, the same three findings
```

Recording the parameter names and matching them to the call site's argument
positions is what makes the two different:

```
#339's file with its fixed message          exit 0
the same file with the interpolation back   exit 1
  whitelist/services/whitelist.py:153 _refuse(e): serves-exception-text
  whitelist/services/whitelist.py:159 _refuse(e): serves-exception-text
  whitelist/services/whitelist.py:171 _refuse(e): serves-exception-text
```

So a finding means *the caught exception landed on a parameter that reaches the
message*, not *the caught exception was handed to a function that builds
exceptions*. `_refuse` as it stands is not a finding, and that is a useful thing
for the gate to be able to say.

**What none of the three rules covers.** A field written outside a handler from a
value that travelled there in some other way; a serializer that builds a string in
a `SerializerMethodField` rather than exposing a model field; API-exception
helpers two calls deep or using indirect parameter aliases, since that rule
checks one direct boundary. Model-note helpers are followed separately. Method
names are conservative approximations; runtime receiver types and rebinding of
allowlisted variable names still require review.

**The allowlist checks its own claims.** Each entry names a model and a field, and
the gate refuses when a serializer of that model does in fact expose it — so an
entry cannot quietly become false as serializers change. This checks the named
field's visibility, not the receiver's runtime identity.

The subclass set is collected from the source, following `APIException` through
subclassing, so a new exception module is covered without an edit. It is 70
classes today.

`LEGACY` is empty, and the way it emptied is the point of it being there. It
held the five sites in `wallets/services/transfers.py` — the native and ERC-20
send paths — which moved in their own PR because that file is on the
owner-merge list, and [#274](https://github.com/RonildoBraga/ledova/pull/274)
fixed them the same way as the eighteen here. **The list is shrink-only in both
directions**: a pinned count that is higher than what is there fails as loudly
as one that is lower, so on the first run after rebasing onto a `main` that
contained #274 the gate refused itself —

```
These pinned counts are higher than what is there (1):
  backend/wallets/services/transfers.py: pinned 5, found 0
```

— rather than carrying a satisfied pin until somebody wondered what it was
guarding. A list that only watches for growth cannot tell a paid debt from an
unmeasured one.

## The logging privacy gate

`scripts/check-logging.py` is the mechanical half of "never log an email
address or a token". `make check-logging` runs it, `make check` includes it, and
CI runs it in the source-gates job. Like the other two it needs no dependencies:
Python 3 and a checkout are enough. `make test-gates` runs its unit tests in
`scripts/tests/`, which is the evidence that it fires rather than merely runs.

It enforces five rules, each chosen because it is decidable from the syntax
alone. A gate that has to guess what a value holds at run time is a gate that
gets allowlisted into meaninglessness.

Clients -- `dashboard/src`, `mobile/src`, `packages/shared/src` and
`marketing/src`, by the same TypeScript and JavaScript extensions the comment
gate uses. Every argument of `console.assert`, `console.debug`, `console.dir`,
`console.error`, `console.info`, `console.log`, `console.table`,
`console.trace` and `console.warn` must be one string literal or one template
literal, and no template may reach for `JSON.stringify`. That stops the whole
object arriving, and `String(axiosError)` is the error's message rather than its
request. An argument that is a plain string variable is refused too. That is the
price of the rule being decidable, and the fix is to inline it into the template.

A literal alone is not sufficient, because a template can reach into the object
the rule was meant to exclude. So a fourth rule refuses a template that
interpolates `.body`, `.config`, `.data`, `.params`, `.request` or `.response`,
which is how an AxiosError's serialised request body is reached. Nothing in the
tree does this today; the rule exists because
``console.error(`API failed: ${error.config?.data}`)`` prints a failed sign-in's
password and passes every other rule here.

Backend -- every `.py` under `backend/`. No call on a `logger`, `logging` or
`log` object may reference an email address, a password or a push token, where
"reference" means an expression whose own syntax names one: the attribute
`.email`, `.password` or `.push_token`; a bare name `email`, `password` or
`push_token`; or a constant string subscript with one of those keys. Positional
arguments, keyword arguments and f-string substitutions are all walked.

Backend, second rule -- no logging call may hand a whole provider response body
to the formatter. Naming a field is a decision about what an operator needs; a
whole body is whatever the provider chose to send, and for a KYC provider that
is the applicant dossier: legal name, date of birth, residential address,
document number, email address. The syntax that says "whole body" is a bare
name from the gate's `BODY_NAMES` (`response`, `payload`, `body`, `data`,
`result`, `error_body`, `webhook_data`, `applicant_data`, `status_data` and the
rest), a `.text`, `.content`, `.data`, `.details` or `.body` attribute, a
`.json()` call, or a constant subscript or `.get()` of one of those keys --
reached directly or through `str()`, `repr()`, `json.dumps()` or `.format()`.
A provider also puts whole sub-documents under its own keys, and those are
bodies too: `SUB_BODY_KEYS` carries `info`, `review`, `reviewResult`,
`applicant`, `applicantData`, `fixedInfo`, `idDocs` and `addresses`, which is
where SumSub keeps `firstName`, `lastName`, `dob`, `idDocs` and `addresses`.
`response['info']` is refused for the same reason `response['data']` is.

The rule looks only at the value handed to the formatter, so
`f"{response.status_code}"` and `f"{ticket.get('id')}"` are fine and
`f"{response}"` is not. A body-shaped key is refused **whatever the receiver**,
so `unrelated['data']` is a finding: a false positive here is loud and costs a
rename, while requiring the receiver to be a known body name would make the
rule silent on every dictionary the gate has not been told about. A dossier key
is the other way round -- `response.info` is refused and `unrelated.info` is
not -- because `.info` is too common an attribute to refuse on its own.

Both backend rules follow **one assignment**. A value bound once in the
enclosing scope and then logged is the value it was bound to, so

```python
line = f"[SUMSUB_CLIENT] Applicant data for {applicant_id}: {response}"
logger.info(line)
```

is refused exactly as the one-line form is, and `addr = user.email` followed by
`f"{addr}"` is refused as `f"{user.email}"` is. Three limits keep that
decidable: a name assigned more than once in the scope is not followed at all,
the substitution is one hop from a logged position rather than a chase through
a chain, and only the structure of the bound expression is descended --
f-strings, `%` operands and container literals -- never the arguments of a call
it makes. So `u = build(user)` then `f"{u.pk}"` is not a finding, and neither is
a field read of a field read.

Container literals are walked wherever they appear, including `extra=`, so
`logger.info("x", extra={"r": response})` is refused.

Backend, third rule -- a logger must be bound to `logger`, `log` or `logging`.
The gate only recognises calls on those three names, so a module binding its
logger to anything else is not scanned at all, and nothing would say so. That
is the failure argued against under [Clients and the shared
package](ARCHITECTURE.md#clients-and-the-shared-package): *for a gate, prefer
the failure that shouts.* Binding `audit = logging.getLogger("audit")` is a
finding naming the binding. The same
rule covers subscripts, annotated assignments, assignment expressions and
chained targets. Tuple and list assignments pair targets with values, including
nested pairs. An uninspectable mapping or container cannot silently hide a
logger: bind it directly to a scanned name instead. `SumSubService.get_applicant_data` and
`get_applicant_status` log the applicant id and the review answer, which is
what `IdentityVerificationService.get_verification_status` polls them for;
`ExpoPushClient` logs the Expo error code rather than the ticket, whose
`message` and `details` both echo the push token.

What it does not cover, deliberately. `print` and a management command's
`self.stdout.write` are ungated: every `print` in `backend/` is a data
migration reporting what it moved -- the progress counters in
`assets/migrations/0009_...` and the backfill counts in the RLS stage R0
migrations -- and no command writes an address. That is a convention held by
review rather than by a check, and it is the kind of sentence that goes stale
between the day it is written and the next migration; if a `print` ever carries
a row's contents rather than a count of rows, nothing here will say so. An object whose `__str__` returns an email -- `CustomUser.__str__`
does -- is ungated too: `f"{user}"` in a log line is a leak the syntax cannot
tell apart from `f"{token}"`, and no site does it today. `contracts/`,
`packages/scripts/` and the root build config of each client are outside the
client trees; they are build tooling that never holds a user's request. The
client scanner lexes strings, templates, comments and regex literals so that a
`console.error(` inside any of them is not a call, but it has no JSX mode: an
apostrophe in JSX text can hide the rest of that line from it. Console calls sit
on their own lines, so that costs nothing today, and a call hidden that way
would be a false negative, never a false positive. Nor does anything reach the
content of a string field: a provider's own error message -- Expo's is
`"ExponentPushToken[...]" is not a registered push notification recipient
device` -- is a `str` like any other, so `ticket.get('message')` is refused
only by review, not by the gate. The same holds on the clients, where the
literal-only rule certifies a template whatever it interpolates:
`mobile/src/components/ErrorBoundary.tsx` logs `error.message` and
`info.componentStack`, and
`mobile/src/screens/signup/identity-verification/components/VerificationFormModal.tsx`
logs the `message` of a WebView `postMessage`. Both are provider- or
SDK-authored strings today; if one ever carries user input, the gate will not
say so.

Two further backend gaps are known and deliberate. A value assigned **twice**
in a scope is not followed, so a body reached through a reassigned name passes;
following it would mean tracking which branch ran, which is not decidable from
syntax. And a body reached through a **call** the gate does not recognise --
`logger.info(f"{summarise(response)}")` -- passes, because `summarise` may
return an id as easily as a dossier; only `str`, `repr`, `json.dumps`,
`pprint`, `pformat` and `.format` are followed through. Both are false
negatives that a reviewer has to catch, and both are stated here rather than
left for the next person to rediscover.

## Shared TypeScript types

`packages/shared/eslint.config.js` applies `eslint-naming-rules.js` to
`src/types/**/*.ts`. Two rules are live there. The naming-convention rule is an
error:

- Interfaces and type aliases are `PascalCase`, no underscores. The custom
  regex is `^[A-Z][a-zA-Z0-9]*$`, so a digit anywhere after the first character
  is fine (`EIP712Domain` in `src/types/domain/trading.ts` passes).
- Properties are `camelCase`, except the query-parameter and API-field names
  listed in the rule's filter (`page`, `page_size`, `order_by`, `start_date`,
  `end_date`, `min_*`, `max_*`, `is_*`, `has_*`, `*_uuid`, `*_id`, `*_at`,
  `*_type`, `*_status`, `contract_address`, `user_account` and the rest).
- Enum members are `UPPER_CASE` or `PascalCase`.

The query-parameter rule is a warning: inside a `*QueryParams` or `*Filters`
interface, `minValue`, `maxValue`, `startDate`, `endDate`, `searchQuery`,
`orderBy` and `pageSize` warn, because query parameters use snake_case to match
the URL.

Two conventions in the same file are **not** enforced. Prefer a utility type
over the entity to a `*Payload`, `Create*` or `Update*` interface, for example
`type CreateEntity = Omit<Entity, 'uuid'>`; the `Signin`, `Signup`,
`EmailVerification`, `TokenRefresh` and `GenerateDocument` payloads are the
intended exceptions. `eslint-naming-rules.js` does declare
`noEntityPayloadRule` and `useUtilityTypesRule` for these, but all three
restricted-syntax rules use the same `no-restricted-syntax` key and the object
spread building `namingConventions` keeps only the last, so only the
query-parameter rule reaches eslint. `CreateFavouriteAsset`,
`UpdateUserPreferences` and `CreateOrderRequest` already lint clean under
`src/types/`. Fixing that means merging the three selectors into one
`no-restricted-syntax` entry, then cleaning up what it flags: a code change,
not a documentation one.

Naming patterns the existing types follow: an entity is the bare name (`Asset`,
`Wallet`, `Portfolio`, `UserProfile`); a query-parameter interface is
`{Entity}QueryParams`; a non-CRUD request is `{Action}Request` and its reply
`{Action}Response`. Compose query parameters from the base types in
`packages/shared/src/types/api.ts` rather than repeating their fields:
`PaginationParams` (`page`, `page_size`), `LimitParams` (`limit`, `offset`),
`OrderingParams` (`order_by`), `DateRangeParams` (`start_date`, `end_date`),
`BaseQueryParams` (pagination plus ordering) and `TimeSeriesQueryParams`
(limit, ordering, date range plus `max_points`).
