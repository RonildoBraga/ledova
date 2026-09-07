import ast
import importlib.util
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR).parent
GATE = REPO_ROOT / "scripts" / "check-layers.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_layers", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


def rules_for(source, layer):
    return sorted(rule for _, rule in gate.findings_for(ast.parse(source), layer))


class ModelLayerRuleTest(SimpleTestCase):

    def test_a_classmethod_reading_its_own_manager_is_allowed(self):
        source = """
class Operator:
    @classmethod
    def get(cls):
        operator, _ = cls.objects.get_or_create(pk=1)
        return operator
"""
        self.assertEqual(rules_for(source, "models"), [])

    def test_a_method_naming_its_own_class_is_allowed(self):
        source = """
class Operator:
    def save(self):
        if Operator.objects.filter(pk=1).exists():
            raise ValueError
"""
        self.assertEqual(rules_for(source, "models"), [])

    def test_reaching_another_models_manager_is_flagged(self):
        source = """
class ReviewRequest:
    def calculate_dilution(self):
        return ShareIssuance.objects.completed_supply(self.token)
"""
        self.assertEqual(rules_for(source, "models"), [gate.MODEL_QUERY])

    def test_a_nested_meta_class_does_not_lose_the_models_own_name(self):
        source = """
class Operator:
    class Meta:
        ordering = ["name"]

    @classmethod
    def first_one(cls):
        return Operator.objects.first()
"""
        self.assertEqual(rules_for(source, "models"), [])

    def test_a_query_outside_any_class_is_flagged(self):
        source = """
DEFAULTS = Country.objects.all()
"""
        self.assertEqual(rules_for(source, "models"), [gate.MODEL_QUERY])

    def test_a_second_model_defined_in_the_same_file_does_not_excuse_the_first(self):
        source = """
class Holding:
    def value(self):
        return Snapshot.objects.first()


class Snapshot:
    pass
"""
        self.assertEqual(rules_for(source, "models"), [gate.MODEL_QUERY])


class ViewLayerRuleTest(SimpleTestCase):

    def test_atomic_decorating_a_drf_write_hook_that_only_delegates_is_allowed(self):
        source = """
class ThingViewSet:
    @transaction.atomic
    def create(self, request):
        return super().create(request)
"""
        self.assertEqual(rules_for(source, "views"), [])

    def test_atomic_on_a_write_hook_that_orchestrates_is_flagged(self):
        source = """
class ThingViewSet:
    @transaction.atomic
    def create(self, request):
        existing = self.get_queryset().first()
        serializer = self.get_serializer(existing, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_TRANSACTION])

    def test_atomic_delegating_to_a_different_hook_is_flagged(self):
        source = """
class ThingViewSet:
    @transaction.atomic
    def create(self, request):
        return super().update(request)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_TRANSACTION])

    def test_an_atomic_block_in_a_view_body_is_flagged(self):
        source = """
class ThingViewSet:
    def create(self, request):
        with transaction.atomic():
            return super().create(request)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_TRANSACTION])

    def test_atomic_decorating_a_perform_hook_is_flagged(self):
        source = """
class ThingViewSet:
    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_TRANSACTION])

    def test_select_for_update_is_allowed_in_get_queryset_only(self):
        allowed = """
class ThingViewSet:
    def get_queryset(self):
        queryset = Thing.objects.visible_to_user(self.request.user)
        if self.action in {"update", "partial_update"}:
            return queryset.select_for_update()
        return queryset
"""
        flagged = """
class ThingViewSet:
    def update(self, request):
        row = self.get_queryset().select_for_update().first()
        return row
"""
        self.assertEqual(rules_for(allowed, "views"), [])
        self.assertEqual(rules_for(flagged, "views"), [gate.VIEW_LOCK])

    def test_a_scoped_queryset_is_allowed_but_a_bare_manager_is_not(self):
        scoped = """
class ThingViewSet:
    def get_queryset(self):
        return Thing.objects.visible_to_user(self.request.user)
"""
        bare = """
class ThingViewSet:
    def get_queryset(self):
        return Thing.objects.filter(active=True)
"""
        self.assertEqual(rules_for(scoped, "views"), [])
        self.assertEqual(rules_for(bare, "views"), [gate.VIEW_ORM])

    def test_an_unguarded_lock_in_get_queryset_is_flagged(self):
        source = """
class ThingViewSet:
    def get_queryset(self):
        return Thing.objects.visible_to_user(self.request.user).select_for_update()
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_LOCK])

    def test_a_lock_guarded_by_a_getattr_action_check_is_allowed(self):
        source = """
class ThingViewSet:
    def get_queryset(self):
        queryset = Thing.objects.visible_to_user(self.request.user)
        if getattr(self, "action", None) in {"update"}:
            return queryset.select_for_update()
        return queryset
"""
        self.assertEqual(rules_for(source, "views"), [])

    def test_a_logger_in_a_view_is_flagged(self):
        source = """
logger = logging.getLogger(__name__)


class ThingViewSet:
    def get_queryset(self):
        return Thing.objects.visible_to_user(self.request.user)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_LOGGER])

    def test_an_unscoped_branch_beside_a_scoped_one_is_flagged(self):
        source = """
class ThingViewSet:
    def get_queryset(self):
        if self.request.user.is_staff:
            return Thing.objects.all()
        return Thing.objects.visible_to_user(self.request.user)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_ORM])

    def test_a_class_level_queryset_attribute_is_examined(self):
        source = """
class ThingViewSet:
    queryset = Thing.objects.all()

    def get_queryset(self):
        return Thing.objects.visible_to_user(self.request.user)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_ORM])

    def test_scoping_carried_on_a_local_variable_is_allowed(self):
        source = """
class ThingViewSet:
    def get_queryset(self):
        queryset = Thing.objects.with_relations()
        if self.action in MANAGE:
            return queryset.manageable_by_user(self.request.user)
        return queryset.visible_to_user(self.request.user)
"""
        self.assertEqual(rules_for(source, "views"), [])

    def test_a_scoping_call_in_the_arguments_scopes_the_expression(self):
        source = """
class ThingViewSet:
    def get_queryset(self):
        return Thing.objects.in_directory().filter(company__in=eligible_investor_companies(self.request.user))
"""
        self.assertEqual(rules_for(source, "views"), [])

    def test_filtering_a_second_model_by_a_row_from_get_object_is_still_flagged(self):
        source = """
class ThingViewSet:
    def issuances(self, request, uuid=None):
        token = self.get_object()
        return ShareIssuance.objects.filter_by_token(token)
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_ORM])

    def test_a_scoping_name_mentioned_elsewhere_no_longer_excuses_the_function(self):
        source = """
class ThingViewSet:
    def leaky(self):
        if self.request.user.is_staff:
            return Other.objects.all()
        return self.get_queryset()
"""
        self.assertEqual(rules_for(source, "views"), [gate.VIEW_ORM])


class CallReceiverTest(SimpleTestCase):

    def test_a_manager_reached_through_a_call_is_still_a_query_in_a_model(self):
        source = """
class Thing:
    def owner(self):
        return get_user_model().objects.first()
"""
        self.assertEqual(rules_for(source, "models"), [gate.MODEL_QUERY])

    def test_apps_get_model_is_still_a_query_in_a_model(self):
        source = """
class Thing:
    def other(self):
        return apps.get_model("app", "Other").objects.all()
"""
        self.assertEqual(rules_for(source, "models"), [gate.MODEL_QUERY])

    def test_type_self_is_the_models_own_manager(self):
        source = """
class Thing:
    def bind(self):
        return type(self).objects.filter(pk=self.pk)
"""
        self.assertEqual(rules_for(source, "models"), [])


class PinnedCountsTest(SimpleTestCase):

    def test_every_allowed_entry_carries_a_count_and_a_reason(self):
        for key, value in gate.ALLOWED.items():
            count, reason = value
            self.assertGreater(count, 0, key)
            self.assertGreater(len(reason), 60, key)

    def test_no_key_is_both_a_stated_exception_and_backlog(self):
        self.assertEqual(set(gate.ALLOWED) & set(gate.LEGACY), set())

    def test_every_pinned_rule_is_a_rule_the_gate_has(self):
        for key in list(gate.ALLOWED) + list(gate.LEGACY):
            self.assertIn(key.rsplit(":", 1)[1], gate.RULES, key)


class TaskLayerRuleTest(SimpleTestCase):

    def test_a_task_opening_its_own_transaction_is_flagged(self):
        source = """
@app.task
def sync(uuid):
    with transaction.atomic():
        do_the_thing(uuid)
"""
        self.assertEqual(rules_for(source, "tasks"), [gate.TASK_TRANSACTION])

    def test_a_task_that_calls_one_service_is_allowed(self):
        source = """
@app.task
def sync(uuid):
    return sync_wallet(uuid)
"""
        self.assertEqual(rules_for(source, "tasks"), [])


class AdminLayerRuleTest(SimpleTestCase):

    def test_a_bare_admin_view_is_flagged(self):
        source = """
class ThingAdmin:
    def get_urls(self):
        return [path("<uuid:uuid>/act/", self.admin_site.admin_view(self.act_view), name="act")]
"""
        self.assertEqual(rules_for(source, "admin"), [gate.ADMIN_BARE_VIEW])

    def test_a_row_action_through_the_helper_is_allowed(self):
        source = """
class ThingAdmin:
    def get_urls(self):
        return [admin_action_path(self, "<uuid:uuid>/act/", "act", self.act_view)]
"""
        self.assertEqual(rules_for(source, "admin"), [])

    def test_the_wrapper_is_flagged_however_the_route_is_built(self):
        source = """
class ThingAdmin:
    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [path("<uuid:uuid>/act/", wrap(self.act_view), name="act")]
"""
        self.assertEqual(rules_for(source, "admin"), [gate.ADMIN_BARE_VIEW])


class LayerDiscoveryTest(SimpleTestCase):

    def layer_of(self, relative):
        return gate.layer_of(gate.BACKEND / relative)

    def test_an_admin_package_and_an_admin_module_are_both_the_admin_layer(self):
        self.assertEqual(self.layer_of("tokens/admin/share_token.py"), "admin")
        self.assertEqual(self.layer_of("whitelist/admin.py"), "admin")

    def test_the_shared_helpers_are_excluded_by_name_not_by_accident(self):
        self.assertEqual(gate.RULE_HELPERS, ("shared", "utils"))
        self.assertIsNone(self.layer_of("shared/utils/admin_actions.py"))
        self.assertIsNone(self.layer_of("shared/utils/admin_files.py"))
        self.assertIsNone(self.layer_of("shared/utils/admin/anything.py"))

    def test_the_helpers_own_admin_view_call_is_the_reason_that_matters(self):
        source = (gate.BACKEND / "shared/utils/admin_actions.py").read_text()

        self.assertIn("admin_view", source)
        self.assertEqual(rules_for(source, "admin"), [gate.ADMIN_BARE_VIEW])


def signals_in(source):
    return sorted(rule for _, rule in gate.signal_findings(ast.parse(source)))


class SignalRuleTest(SimpleTestCase):

    def test_the_three_import_shapes_are_all_flagged(self):
        self.assertEqual(signals_in("from django.db.models.signals import post_save"), [gate.SIGNAL_IMPORT])
        self.assertEqual(signals_in("import django.db.models.signals"), [gate.SIGNAL_IMPORT])
        self.assertEqual(signals_in("from django.db.models import signals"), [gate.SIGNAL_IMPORT])

    def test_an_aliased_import_is_still_the_same_import(self):
        self.assertEqual(signals_in("import django.db.models.signals as s"), [gate.SIGNAL_IMPORT])
        self.assertEqual(signals_in("from django.db.models import signals as s"), [gate.SIGNAL_IMPORT])

    def test_the_ordinary_model_imports_are_not_flagged(self):
        self.assertEqual(signals_in("from django.db import models"), [])
        self.assertEqual(signals_in("from django.db.models import Q"), [])
        self.assertEqual(signals_in("from django.db import transaction"), [])

    def test_the_rule_reads_imports_so_a_string_import_goes_past_it(self):
        self.assertEqual(signals_in("importlib.import_module('django.db.models.signals')"), [])

    def test_the_one_sanctioned_receiver_is_the_only_allowed_entry_for_this_rule(self):
        keys = [key for key in gate.ALLOWED if key.endswith(f":{gate.SIGNAL_IMPORT}")]

        self.assertEqual(keys, ["backend/shared/apps.py:django-signals"])
        self.assertEqual(gate.ALLOWED[keys[0]][0], 1)

    def test_the_sanctioned_receiver_is_where_the_allowed_entry_says_it_is(self):
        source = (gate.BACKEND / "shared/apps.py").read_text()

        self.assertEqual(signals_in(source), [gate.SIGNAL_IMPORT])
        self.assertIn("post_delete.connect", source)

    def test_the_backend_walk_reaches_beyond_the_four_layers(self):
        walked = {path.relative_to(gate.BACKEND) for path in gate.backend_files()}

        self.assertIn(Path("shared/apps.py"), walked)
        self.assertIn(Path("shared/storage.py"), walked)
        self.assertTrue(all("tests" not in part.parts for part in walked))
        self.assertTrue(all("migrations" not in part.parts for part in walked))
