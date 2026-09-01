# Ledova Development Patterns

This document describes the core development patterns used in the Ledova Django backend.

## Architecture Overview

Ledova follows a layered architecture with clear separation of concerns:

```
Views (API) → Serializers → Services (Business Logic) → QuerySets (Data Access) → Models
                                  ↓                                                   ↓
                            Exceptions (Error Handling)                     Signals (Side Effects)
                                  ↓
                            Logging (Observability)
                                  ↑
                            Tasks (Background Jobs)
```

## Views

Views handle HTTP requests, delegate to services, and use querysets for data access. They inherit from base viewsets and stay thin.

### Base ViewSets

```python
from shared.views.base import AuthenticatedModelViewSet, AuthenticatedReadOnlyViewSet

# Full CRUD - for user-owned resources
class WalletViewSet(AuthenticatedModelViewSet):
    ...

# Read-only - for reference data
class AssetViewSet(AuthenticatedReadOnlyViewSet):
    ...
```

| Base Class | Use Case |
|------------|----------|
| `AuthenticatedModelViewSet` | Full CRUD for user resources |
| `AuthenticatedReadOnlyViewSet` | Read-only authenticated data |
| `AuthenticatedReferenceDataViewSet` | List/retrieve reference data |
| `PublicReferenceDataViewSet` | Public reference data (no auth) |

### Pattern

```python
# app/views/model.py
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from app.filters import ModelFilter
from app.models import Model
from app.serializers import ModelSerializer
from app.services import ModelService
from shared.views.base import AuthenticatedModelViewSet

class ModelViewSet(AuthenticatedModelViewSet):
    serializer_class = ModelSerializer
    filterset_class = ModelFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "name", "status"]

    def get_queryset(self):
        """Permission scoping only — filtering/ordering/pagination handled by DRF."""
        if self.action in ("create", "update", "partial_update", "destroy"):
            return Model.objects.manageable_by_user(self.request.user)
        return Model.objects.visible_to_user(self.request.user).with_optimized_data()

    def perform_create(self, serializer):
        """Add logic before save (validation, defaults)."""
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"], url_path="do-something")
    def do_something(self, request, uuid=None):
        """Custom action - delegate to service."""
        obj = self.get_object()

        # Service handles business logic, raises exceptions
        result = ModelService.do_something(obj, request.data.get("param"))

        return Response(result, status=status.HTTP_200_OK)
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `get_queryset()` | Permission scoping + data optimization only |
| `filterset_class` | Django-filter FilterSet for query param filtering |
| `ordering` / `ordering_fields` | Default + allowed sort fields (DRF OrderingFilter) |
| `perform_create()` | Pre-save logic (set owner, defaults) |
| `@action` | Custom endpoints beyond CRUD |

### Guidelines

- **Inherit from base viewsets** — provides auth, uuid lookup, consistent behavior
- **Use `filterset_class`** for query param filtering — no manual `query_params.get()` extraction
- **Set `ordering` and `ordering_fields`** — DRF's OrderingFilter handles sorting
- **Keep `get_queryset()` thin** — only permission scoping (`visible_to_user` / `manageable_by_user`) and optimization (`with_optimized_data`)
- **DRF pagination handles limiting** — never manually slice querysets (no `[:100]`)
- **Delegate to services** — views don't contain business logic
- **Raise exceptions** — don't catch and re-wrap; let DRF handle them
- **Use `self.get_object()`** — handles 404 and permission checks automatically

### Custom Actions with Pagination

```python
@action(detail=True, methods=["get"], url_path="related-items")
def related_items(self, request, uuid=None):
    obj = self.get_object()
    queryset = RelatedItem.objects.filter(parent=obj).order_by("-created_at")
    serializer = RelatedItemSerializer(self.paginate_queryset(queryset), many=True)
    return self.get_paginated_response(serializer.data)
```

**Reference**: `wallets/views/wallet.py`, `companies/views/document.py`

## Service Layer

Services contain business logic and are the primary place for complex operations. They use static methods and raise domain-specific exceptions.

### Pattern

```python
# app/services/feature.py
import logging
from shared.utils.logging_utils import LoggingContext
from app.exceptions import SomeBusinessException

logger = logging.getLogger("ledova_backend")

class FeatureService:
    @staticmethod
    def do_something(model_instance, param):
        """
        Brief description of what this does.

        Raises:
            SomeBusinessException: When business rule is violated
        """
        logger.info(f"{LoggingContext.RELEVANT_CONTEXT} Starting operation for {model_instance}")

        # Validate business rules
        if not model_instance.is_valid:
            raise SomeBusinessException("Reason for failure")

        # Perform operation
        result = model_instance.update(param)

        logger.info(f"{LoggingContext.RELEVANT_CONTEXT} Operation completed")
        return result
```

### Guidelines

- Use `@staticmethod` for stateless operations
- Raise domain-specific exceptions (see Exceptions section)
- Log at entry, exit, and error points
- Document which exceptions can be raised
- Keep services focused on a single domain

**Reference**: `wallets/services/transfers.py`, `portfolios/services/sync.py`

## QuerySets, Managers & Filtering

### Filtering with django-filter

API query parameter filtering is handled by `django-filter` FilterSet classes. Each app with API views has a `filters.py` file.

```python
# app/filters.py
import django_filters
from app.models import Model

class ModelFilter(django_filters.FilterSet):
    # Simple field lookups
    status = django_filters.CharFilter()
    company_uuid = django_filters.UUIDFilter(field_name="company__uuid")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    # Date ranges
    start_date = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    end_date = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    # Complex filters delegate to queryset methods
    search = django_filters.CharFilter(method="filter_search")

    def filter_search(self, queryset, name, value):
        return queryset.search(value)

    class Meta:
        model = Model
        fields = []
```

### View Pattern

Views use `filterset_class` for filtering, `ordering`/`ordering_fields` for sorting. DRF pagination handles limiting. `get_queryset()` only handles permission scoping and data optimization.

```python
from app.filters import ModelFilter

class ModelViewSet(AuthenticatedModelViewSet):
    serializer_class = ModelSerializer
    filterset_class = ModelFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "name", "status"]

    def get_queryset(self):
        # Permission scoping only — filtering/ordering/pagination handled by DRF
        if self.action in ("create", "update", "partial_update", "destroy"):
            return Model.objects.manageable_by_user(self.request.user)
        return Model.objects.visible_to_user(self.request.user).with_optimized_data()
```

### QuerySet Pattern

QuerySets contain only business logic — permission scoping, complex queries, and data optimization. No filtering infrastructure (`filter_fields`, `apply_filters`, `order_by_fields`, `apply_limit`).

```python
from django.db.models import QuerySet

class ModelQuerySet(QuerySet):
    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(user_account__user_profiles__user=user).distinct()

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(user_account__user_profiles__user=user).distinct()

    def active(self):
        return self.filter(is_active=True)

    def search(self, query):
        if not query:
            return self
        return self.filter(Q(name__icontains=query) | Q(code__icontains=query))

    def with_optimized_data(self):
        return self.select_related("related").prefetch_related("many_related")
```

### Manager Pattern

Models use `QuerySet.as_manager()` — no separate manager files needed. Django auto-proxies all public queryset methods.

```python
# app/models/model.py
from app.querysets.model import ModelQuerySet

class Model(BaseModel):
    objects = ModelQuerySet.as_manager()
```

For models that need custom manager methods (rare), use `Manager.from_queryset()`:

```python
# app/managers/model.py (only when custom methods needed)
from django.db import models
from app.querysets.model import ModelQuerySet

class ModelManager(models.Manager.from_queryset(ModelQuerySet)):
    def has_active_for_user(self, user):
        return self.for_user(user).active().exists()
```

### Guidelines

- **Filtering**: Use `django-filter` FilterSet classes. DRF's `DEFAULT_FILTER_BACKENDS` applies them globally.
- **Ordering**: Use `ordering` (default) and `ordering_fields` (allowed) on views. DRF's `OrderingFilter` handles it.
- **Pagination**: DRF's `PageNumberPagination` (25 items/page) handles limiting. No manual slicing.
- **Permissions**: `visible_to_user(user)` for reads, `manageable_by_user(user)` for writes — called in `get_queryset()`.
- **Managers**: Use `QuerySet.as_manager()` on the model. No separate manager file unless custom methods are needed.
- Always use `select_related`/`prefetch_related` for related data.
- Staff/superuser bypass permissions.

**Reference**: `companies/filters.py`, `companies/querysets/document.py`, `companies/views/document.py`

## Exceptions

Use domain-specific exceptions that inherit from DRF's `APIException`. DRF automatically handles them and returns appropriate HTTP responses.

### Pattern

```python
# app/exceptions.py
from rest_framework import status
from rest_framework.exceptions import APIException

class InsufficientBalanceException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Insufficient balance for this operation."
    default_code = "insufficient_balance"

class ResourceNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "The requested resource was not found."
    default_code = "not_found"

class ExternalServiceException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "External service unavailable."
    default_code = "external_service_error"
```

### HTTP Status Code Reference

| Code | Use Case |
|------|----------|
| 400 | Invalid input, business rule violation |
| 403 | Permission denied |
| 404 | Resource not found |
| 409 | Conflict (duplicate, state conflict) |
| 502 | External API failure |
| 503 | Service temporarily unavailable |

### Guidelines

- Create specific exceptions per domain (`wallets/exceptions.py`, `portfolios/exceptions.py`)
- Use semantic names that describe the error condition
- Include helpful default messages
- Views stay clean - just call services and let exceptions propagate
- DRF's global handler converts exceptions to JSON responses

**Reference**: `wallets/exceptions.py`, `portfolios/exceptions.py`

## Logging

Use `LoggingContext` constants for filterable, traceable logs.

### Pattern

```python
import logging
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")

# Info for successful operations
logger.info(f"{LoggingContext.WALLET_TRANSFER} Transfer prepared: {amount} ETH")

# Warning for recoverable issues
logger.warning(f"{LoggingContext.WALLET_TRANSFER} Insufficient balance: {balance}")

# Error with stack trace
logger.error(f"{LoggingContext.WALLET_TRANSFER} Failed: {error}", exc_info=True)
```

### Available Contexts

| Category | Contexts |
|----------|----------|
| Auth | `AUTH`, `USER_SIGNUP`, `USER_SIGNIN`, `TOKEN_MANAGEMENT` |
| Accounts | `ACCOUNTS`, `ACCOUNT_CREATION`, `USER_PROFILE` |
| Portfolios | `PORTFOLIOS`, `PORTFOLIO_CREATION`, `ASSET_HOLDINGS` |
| Wallets | `WALLETS`, `WALLET_SYNC`, `WALLET_TRANSFER`, `WALLET_BALANCE` |
| Compliance | `COMPLIANCE`, `MONITORING`, `RISK_ASSESSMENT` |
| System | `SYSTEM`, `BATCH_JOBS`, `PRICE_UPDATES`, `EXCEPTIONS` |

### Log Filtering

```bash
# Filter by context
grep "[WALLETS:TRANSFER]" logs.txt
grep "[PORTFOLIOS]" logs.txt

# Filter by user
grep "user@example.com" logs.txt | grep "[AUTH"
```

**Reference**: `shared/utils/logging_utils.py`

## Signals

Signals are limited to non-authorization side effects. Authorization is derived from current ownership and membership relationships whenever a query or request runs.

### Pattern

```python
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from shared.utils.logging_utils import LoggingContext
from app.models import Model

logger = logging.getLogger("ledova_backend")

@receiver(post_save, sender=Model)
def record_model_creation(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(f"{LoggingContext.SYSTEM} Created {instance}")
```

### Common Use Cases

| Use Case | Signal | Example |
|----------|--------|---------|
| Auto-assign relations | `post_save` | Add wallet to user's portfolio |
| Lifecycle logging | `post_save` | Record model creation |
| Membership logging | `m2m_changed` | Record users added to an account |

### M2M Changed Pattern

```python
@receiver(m2m_changed, sender=Account.user_profiles.through)
def account_users_changed(sender, instance, action, pk_set, **kwargs):
    if action in ("post_add", "post_remove"):
        logger.info(f"{LoggingContext.ACCOUNTS} Membership changed for {instance}")
```

### Guidelines

- Use signals for non-authorization side effects such as notifications and lifecycle logging
- Derive authorization from current ownership and membership relationships
- Always check `if created:` for create-only logic
- Register signals in `app/signals/__init__.py` and import in `app/apps.py`

### When to Use Signals vs Services

| Signals | Services |
|---------|----------|
| Automatic side effects | Explicit business logic |
| Lifecycle logging | Complex validation |
| Triggered by model save | Called from views |
| Fire-and-forget | Return values needed |

**Reference**: `authentication/signals/user.py`, `wallets/signals/wallet.py`

## Serializers

Serializers handle data transformation between Python objects and JSON. They define which fields are exposed and how related data is presented.

### Pattern

```python
# app/serializers/model.py
from rest_framework import serializers
from app.models import Model, RelatedModel

class ModelSerializer(serializers.ModelSerializer):
    # Read-only computed fields
    related_name = serializers.CharField(source="related.name", read_only=True)
    computed_field = serializers.SerializerMethodField()

    # Related object reference (read-only for response)
    related = serializers.PrimaryKeyRelatedField(read_only=True)

    def get_computed_field(self, obj):
        """Complex logic for computed fields."""
        return obj.some_method() if obj.condition else None

    class Meta:
        model = Model
        fields = (
            "uuid",
            "name",
            "related",
            "related_name",
            "computed_field",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "related_name",
            "computed_field",
            "created_at",
            "updated_at",
        )
```

### Dynamic QuerySet Filtering

For write operations, filter querysets based on user permissions:

```python
class AllocationSerializer(serializers.ModelSerializer):
    portfolio = serializers.PrimaryKeyRelatedField(queryset=Portfolio.objects.none())
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none())

    class Meta:
        model = Allocation
        fields = ("uuid", "portfolio", "asset", "percentage")

    def get_fields(self):
        """Override to filter querysets by user permissions."""
        fields = super().get_fields()
        request = self.context.get("request")
        fields["portfolio"].queryset = Portfolio.objects.visible_to_user(request.user)
        fields["asset"].queryset = Asset.objects.all()
        return fields
```

### Guidelines

- Use `read_only_fields` for auto-generated and computed fields
- Use `SerializerMethodField` for complex logic
- Use `source="related.field"` for simple nested data
- Override `get_fields()` to filter querysets by user permissions
- Keep serializers focused on data transformation, not business logic

**Reference**: `portfolios/serializers/portfolio.py`, `wallets/serializers/wallet.py`

## Background Tasks (procrastinate)

Background tasks use [procrastinate](https://procrastinate.readthedocs.io/), a Postgres-backed task queue. The app object lives in `ledova_backend/procrastinate_app.py`; tasks are defined on the `app.task` decorator on functions in each app's `tasks/` package. Scheduled work uses `@app.periodic(cron=...)`.

### Pattern

```python
# app/tasks/sync.py
import logging
from typing import Any, Dict

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext
from app.models import Model
from app.services import SyncService

logger = logging.getLogger("ledova_backend")


@app.task(retry=RetryStrategy(max_attempts=3, wait=60))
async def sync_model(model_uuid: str) -> Dict[str, Any]:
    try:
        instance = Model.objects.get(uuid=model_uuid)
    except Model.DoesNotExist:
        logger.error(f"{LoggingContext.SYNC} Model not found: {model_uuid}")
        return {"status": "error", "error": "Model not found"}

    result = SyncService.sync(instance)
    logger.info(f"{LoggingContext.SYNC} {model_uuid}: {result}")
    return result


@app.periodic(cron="*/10 * * * *")
@app.task
async def sync_all_models() -> Dict[str, Any]:
    models = Model.objects.filter(is_active=True)
    queued = 0
    for instance in models:
        await sync_model.defer_async(model_uuid=str(instance.uuid))
        queued += 1
    return {"queued": queued}
```

### Decorator options

| Option | Purpose |
|--------|---------|
| `retry=RetryStrategy(...)` | Controls retry count + backoff |
| `@app.periodic(cron=...)` | Schedule the task on a cron expression |
| `name="app.task_name"` | Explicit task name (defaults to dotted path) |

### Guidelines

- Delegate business logic to services; keep task bodies thin.
- Use `.defer_async(**kwargs)` to enqueue; procrastinate passes kwargs, not positional args.
- Task state and the queue itself live in Postgres — no Redis broker, no Celery beat.
- `@app.periodic` handles scheduling; don't stand up a separate scheduler.
- Return a dict for logs; raise on unrecoverable errors so the retry strategy kicks in.

**Reference**: `wallets/tasks/sync.py`, `assets/tasks/sync.py`, `portfolios/tasks/sync.py`

## Transaction Management

Transaction boundaries belong in the **service layer**, not views. A service method represents a unit of work - if any part fails, everything rolls back.

### Pattern

```python
# app/services/accounts.py
from django.db import transaction

class AccountService:
    @staticmethod
    @transaction.atomic
    def create_account(account_data, user_profiles, director_id=None):
        """
        Create account and associate users atomically.

        If any operation fails, all changes are rolled back.
        """
        account = Account.objects.create(**account_data)

        for profile in user_profiles:
            account.user_profiles.add(profile)

        if director_id:
            director = UserProfile.objects.get(pk=director_id)
            if director not in user_profiles:
                raise InvalidOperationException("Director must be associated")
            account.director = director
            account.save(update_fields=["director"])

        return account
```

### Pessimistic Locking

Use `select_for_update()` inside services to prevent race conditions:

```python
# app/services/wallet.py
class WalletService:
    @staticmethod
    @transaction.atomic
    def debit_balance(wallet_uuid, amount):
        """
        Debit wallet balance with row-level locking.

        Raises:
            InsufficientBalanceException: If balance is too low
        """
        wallet = Wallet.objects.select_for_update().get(uuid=wallet_uuid)

        if wallet.balance < amount:
            raise InsufficientBalanceException(f"Balance {wallet.balance} < {amount}")

        wallet.balance -= amount
        wallet.save(update_fields=["balance"])
        return wallet
```

### Upsert Pattern

Handle create-or-update atomically in services:

```python
# app/services/preferences.py
class PreferencesService:
    @staticmethod
    @transaction.atomic
    def update_preferences(user_profile, data):
        """
        Create or update user preferences atomically.

        Uses select_for_update to prevent race conditions on concurrent requests.
        """
        try:
            preferences = UserPreferences.objects.select_for_update().get(
                user_profile=user_profile
            )
            for key, value in data.items():
                setattr(preferences, key, value)
            preferences.save()
        except UserPreferences.DoesNotExist:
            preferences = UserPreferences.objects.create(
                user_profile=user_profile, **data
            )
        return preferences
```

Views stay thin - they just call the service:

```python
# app/views/preferences.py
class PreferencesViewSet(AuthenticatedModelViewSet):
    @action(detail=False, methods=["post"])
    def update_preferences(self, request):
        preferences = PreferencesService.update_preferences(
            request.user.userprofile, request.data
        )
        serializer = self.get_serializer(preferences)
        return Response(serializer.data)
```

### When to Use Transactions

| Scenario | Approach |
|----------|----------|
| Multiple related creates/updates | `@transaction.atomic` on service method |
| Read-then-write (balance, counters) | `select_for_update()` inside service |
| Upsert (create or update) | `select_for_update()` with try/except in service |
| Bulk operations | Wrap loop in `@transaction.atomic` service method |

### Guidelines

- **Always in services**: Transaction logic belongs in services, not views
- **Decorator preferred**: Use `@transaction.atomic` decorator over context manager
- **Lock what you modify**: Use `select_for_update()` for read-then-write patterns
- **Exceptions roll back**: Any exception triggers automatic rollback
- **Keep transactions short**: Long-held locks reduce concurrency

**Reference**: `users/services/accounts.py`, `wallets/services/transfers.py`

## Dependency Injection

Services use static methods for simplicity, but this can make testing harder. This section explains when to use each approach and how to improve testability.

### Current Pattern: Static Methods

```python
# Simple, stateless - good for most cases
class TransferService:
    @staticmethod
    def prepare_transfer(wallet, recipient, amount):
        # Calls external API directly
        blockchain_result = BlockchainAPI.send(recipient, amount)
        return {"tx_hash": blockchain_result.hash}
```

**Pros**: Simple, no instantiation needed, clear intent
**Cons**: Hard to mock `BlockchainAPI` in tests without patching

### Improved Pattern: Constructor Injection

For services with external dependencies, use constructor injection:

```python
# app/services/transfers.py
class TransferService:
    def __init__(self, blockchain_client=None):
        self.blockchain_client = blockchain_client or BlockchainAPI()

    def prepare_transfer(self, wallet, recipient, amount):
        result = self.blockchain_client.send(recipient, amount)
        return {"tx_hash": result.hash}


# In views - use default
class TransferViewSet(AuthenticatedModelViewSet):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.transfer_service = TransferService()

    @action(detail=True, methods=["post"])
    def transfer(self, request, uuid=None):
        wallet = self.get_object()
        result = self.transfer_service.prepare_transfer(
            wallet, request.data["recipient"], request.data["amount"]
        )
        return Response(result)


# In tests - inject mock
class TestTransferService:
    def test_prepare_transfer(self):
        mock_client = Mock()
        mock_client.send.return_value = Mock(hash="0x123")

        service = TransferService(blockchain_client=mock_client)
        result = service.prepare_transfer(wallet, "0xabc", 100)

        assert result["tx_hash"] == "0x123"
        mock_client.send.assert_called_once_with("0xabc", 100)
```

### Protocol Pattern (Type-Safe DI)

For stronger typing, define protocols for dependencies:

```python
# app/protocols.py
from typing import Protocol

class BlockchainClientProtocol(Protocol):
    def send(self, recipient: str, amount: int) -> "TransactionResult": ...
    def get_balance(self, address: str) -> int: ...


# app/services/transfers.py
class TransferService:
    def __init__(self, blockchain_client: BlockchainClientProtocol | None = None):
        self.blockchain_client = blockchain_client or BlockchainAPI()
```

### When to Use Each Approach

| Approach | Use When |
|----------|----------|
| Static methods | Pure business logic, no external dependencies |
| Constructor injection | External APIs, databases, or services that need mocking |
| Protocol + injection | Complex dependencies, multiple implementations |

### Guidelines

- **Start simple**: Use static methods until you need testability
- **Inject at boundaries**: External APIs, third-party services, I/O operations
- **Default to production**: Constructor should default to real implementation
- **Keep views thin**: Instantiate services in `__init__`, not in action methods
- **Use protocols sparingly**: Only when you need multiple implementations or strict typing

**Reference**: Consider refactoring `wallets/services/transfers.py` if mocking becomes difficult

## File Organization

```
app/
├── exceptions.py           # Domain exceptions
├── filters.py              # django-filter FilterSet classes
├── models/
│   ├── __init__.py        # Import models (objects = QuerySet.as_manager())
│   └── model.py
├── querysets/
│   ├── __init__.py
│   └── model.py           # QuerySet per model (business logic only)
├── services/
│   ├── __init__.py
│   └── feature.py         # Service per feature/domain
├── signals/
│   ├── __init__.py        # Import signal handlers
│   └── model.py           # Signals per model
├── serializers/
│   ├── __init__.py
│   └── model.py           # Serializer per model
├── views/
│   ├── __init__.py
│   └── model.py           # ViewSet per model
└── tasks/
    ├── __init__.py
    └── sync.py             # Background tasks per domain
```

## Quick Reference

### Creating a New Feature

1. **Model**: Add to `models/` with `objects = MyQuerySet.as_manager()`
2. **QuerySet**: Create in `querysets/` with permission and business logic methods
3. **FilterSet**: Add to `filters.py` with django-filter fields for API filtering
4. **Signals**: Add non-authorization side effects in `signals/` if needed
5. **Exceptions**: Add domain exceptions to `exceptions.py`
6. **Service**: Create in `services/` with business logic
7. **Serializer**: Create in `serializers/` for data transformation
8. **View**: Create in `views/` with `filterset_class`, `ordering`, `ordering_fields`
9. **Tasks**: Add to `tasks/` for background processing (if needed)

### Code Review Checklist

- [ ] Views inherit from appropriate base viewset
- [ ] Views set `filterset_class`, `ordering`, and `ordering_fields`
- [ ] Views keep `get_queryset()` thin (permission scoping + optimization only)
- [ ] Views delegate complex logic to services
- [ ] FilterSets use `method=` for complex filters (search, OR queries)
- [ ] Models use `QuerySet.as_manager()` (no separate manager file)
- [ ] Serializers use `read_only_fields` for computed/auto fields
- [ ] Serializers filter querysets by user in `get_fields()` for write operations
- [ ] Services raise domain exceptions, not generic ones
- [ ] Logging uses `LoggingContext` prefixes
- [ ] Related data uses `select_related`/`prefetch_related`
- [ ] Exceptions have appropriate HTTP status codes
- [ ] User-owned models derive authorization from current ownership or membership relationships
- [ ] Signals check `if created:` for create-only logic
- [ ] Tasks use `bind=True` and `max_retries` for retry logic
- [ ] Tasks delegate to services, don't contain business logic
- [ ] Transactions are in services, not views
- [ ] Multi-step service methods use `@transaction.atomic`
- [ ] Read-then-write operations use `select_for_update()`
