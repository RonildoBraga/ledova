# Backend conventions

One person maintains this. Prefer fewer layers and fewer lines. Delete before abstracting; add a layer only when a second caller needs the same logic.

The dashboard (`dashboard/`), the mobile app (`mobile/`) and the shared TypeScript packages (`packages/`) are first-class clients: every response key, status code and URL they read is a contract the backend keeps.

## Layers (per app: models/ querysets/ serializers/ services/ views/ tasks/ admin/)

| Layer | Owns | Never contains |
|---|---|---|
| `models/` | fields, `TextChoices`, constraints, `__str__`, properties over own fields, single-row transitions (guard + set fields + `save(update_fields=...)`, <= 10 lines, raise the app's APIException on a bad state) | queries on other models, multi-step workflows, external I/O |
| `querysets/` | every reusable query: `visible_to_user`, `manageable_by_user`, status filters, `select_related` bundles, annotations, aggregates; wired with `objects = XQuerySet.as_manager()` | saves, side effects, calls into services |
| `services/` | orchestration across models, external I/O (chain, KYC, email), `transaction.atomic` + `select_for_update`; the one place a multi-model workflow lives; plain functions or a class of staticmethods | HTTP objects, serializers, `Response` |
| `serializers/` | JSON shape and input validation; scope writable FKs in `get_fields()` with `visible_to_user` | business rules, locking, queries beyond FK scoping |
| `views/` | permissions, `get_queryset()` = `Model.objects.visible_to_user(user)...`, serializer choice, one service call, `Response` | raw `.objects.filter`, try/except that re-wraps an APIException, log lines that restate the request |
| `tasks/` | `@app.task` / `@app.periodic`: load the row by uuid, call one service, return a dict | orchestration, state machines |
| `admin/` | registration, list/search/filter, operator actions that call the same model transition or service the API calls | a second implementation of a workflow, HTML badge builders |

## Rules

- Tenant scoping: every customer-facing queryset has `visible_to_user(user)` (and `manageable_by_user` for writes) returning `none()` for None/anonymous; every viewset calls it in `get_queryset`; writable FKs are scoped in `get_fields()`; owner FKs are NOT NULL. Every new detail route or action gets a cross-tenant test (a row in `ROUTES` in `shared/tests/test_cross_tenant_routes.py`, or the app's own tests).
- No Django signals. A side effect is an explicit call in the service (or `perform_create`) that creates the row.
- No new `managers/` packages. The only Manager is `CustomUserManager` in `authentication/managers/` (create_user, create_superuser, email resolution); everything else is a queryset wired with `as_manager()`.
- Exceptions: one `exceptions.py` per app containing only classes that are raised; no `__init__` that merely forwards `detail`; use DRF `NotFound`/`PermissionDenied`/`ValidationError` for plain 404/403/400. Error bodies carry `detail` (auth failures also `error` and `code`); clients read `detail`.
- Logging: `logging.getLogger(__name__)`, no prefix constants; log errors in services and tasks, not requests in views; never log emails or tokens.
- Constants: `TextChoices` next to the model; numeric thresholds as module constants in the app's `constants.py`.
- Comments and docstrings only when they say what the name and signature do not (why, units, external contract). No section banners, no Args/Returns blocks, no help_text that restates the field name.
- Tests: `APITestCase` under `<app>/tests/`; superusers via `create_superuser`; `make test` runs SQLite locally, CI also runs the migration-stage tests and the whole suite on PostgreSQL.
- Migrations: one per model change; never edit an applied one; on testnet, unapplied ones may be deleted.
- Dependencies: nothing in `requirements.txt` or a `package.json` without an importer.
- Endpoints: nothing routed without a caller in `dashboard/`, `mobile/`, `packages/` or a documented external consumer.

## When NOT to add a layer

- A service method with one caller that only forwards to the ORM: put the query in `querysets/` and call it from the view.
- A queryset method with one call site: inline the filter.
- A base class or mixin for one subclass; an exception class for one raise that DRF already covers; a manager for a queryset.
- A task that is never deferred; a periodic task for a one-off backfill (use a management command or the shell).
- A model, column or endpoint that records data nothing reads.
