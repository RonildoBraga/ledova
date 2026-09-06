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

    def test_atomic_decorating_a_drf_write_hook_is_allowed(self):
        source = """
class ThingViewSet:
    @transaction.atomic
    def create(self, request):
        return super().create(request)
"""
        self.assertEqual(rules_for(source, "views"), [])

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
        return Thing.objects.visible_to_user(self.request.user).select_for_update()
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
