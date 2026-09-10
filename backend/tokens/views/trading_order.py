from uuid import UUID

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    PolymorphicProxySerializer,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from shared.utils import get_client_ip
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.exceptions import (
    OrderActionRefreshRequiredException,
    SwapExpiredException,
    SwapNotReadyException,
)
from tokens.filters import TransferOrderFilter
from tokens.models import OrderActionPurpose, OrderSubmissionStatus, TransferOrder
from tokens.serializers import (
    TransferOrderCreateSerializer,
    TransferOrderDetailSerializer,
    TransferOrderListSerializer,
)
from tokens.serializers.order_action import (
    ORDER_ACTION_RESPONSES,
    OrderActionContextSerializer,
    OrderActionExecuteRequestSerializer,
    OrderActionIdentitySerializer,
    OrderActionLookupSerializer,
    OrderActionModifyRequestSerializer,
    OrderActionSubmissionSerializer,
    action_snapshot,
)
from tokens.serializers.order_submission import (
    OrderSubmissionLookupSerializer,
    OrderSubmissionSerializer,
    SignedOrderSubmissionSerializer,
    submission_snapshot,
)
from tokens.serializers.swap_order import (
    SettlementApprovalBroadcastSerializer,
    SettlementIdentitySerializer,
    SettlementSignatureSerializer,
    SettlementWriteIdentitySerializer,
    SubmitSignatureSerializer,
    SwapOrderDetailSerializer,
)
from tokens.serializers.trading_responses import (
    ApprovalDataResponseSerializer,
    ApprovalStatusResponseSerializer,
    SettlementApprovalReceiptSerializer,
    SettlementApprovalStatusSerializer,
    SettlementApprovalUncertainSerializer,
    SwapSignatureRequestSerializer,
)
from tokens.services import (
    AtomicSwapService,
)
from tokens.services.atomic_swap_service import sign_and_execute_swap
from tokens.services.order_actions import (
    execute_order_action,
    issue_order_action,
    order_action_context,
    recover_order_action,
)
from tokens.services.order_modification_service import get_modification_history
from tokens.services.settlement_context import (
    SettlementApprovalUncertain,
    SettlementContextChanged,
    SettlementContextRequired,
)
from tokens.services.trading_order_access import (
    require_pending_settlement,
    resolve_exact_swap_context,
    resolve_order_swap_context,
)
from tokens.services.trading_order_create import (
    execute_order_submission,
    issue_order_submission,
    recover_order_submission,
)
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class TradingOrderViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = TransferOrderListSerializer
    filterset_class = TransferOrderFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "order_type"]
    throttle_scope = "order_write"

    def get_queryset(self):

        return TransferOrder.objects.with_relations().visible_to_user(self.request.user)

    def get_serializer_class(self):
        if self.action == "create_order":
            return SignedOrderSubmissionSerializer
        if self.action == "create_message":
            return TransferOrderCreateSerializer
        if self.action == "retrieve":
            return TransferOrderDetailSerializer
        return TransferOrderListSerializer

    @extend_schema(
        responses={
            200: OrderSubmissionSerializer,
            201: OrderSubmissionSerializer,
            400: OpenApiResponse(
                response={
                    "anyOf": [
                        {"$ref": "#/components/schemas/OrderSubmission"},
                        {"type": "object", "additionalProperties": {}},
                    ]
                },
                description="A recorded business refusal snapshot, or an ordinary request/challenge validation error.",
            ),
            401: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Authentication required."),
            403: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Signature refused."),
            404: OpenApiResponse(response=OpenApiTypes.OBJECT, description="No currently authorized submission."),
            409: OpenApiResponse(
                response=OpenApiTypes.OBJECT, description="Original terms conflict or challenge spent."
            ),
            429: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Request throttle exceeded."),
            500: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Unknown outcome; recover before retrying."),
            503: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Service failure; recover before retrying."),
        }
    )
    @action(detail=False, methods=["post"], url_path="create")
    def create_order(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = execute_order_submission(request.user, serializer.validated_data)
        if result.submission.status == OrderSubmissionStatus.REFUSED:
            response_status = status.HTTP_400_BAD_REQUEST
        else:
            response_status = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(submission_snapshot(result.submission), status=response_status)

    @extend_schema(request=OrderActionExecuteRequestSerializer, responses=ORDER_ACTION_RESPONSES)
    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        return self._execute_action(request, uuid, OrderActionPurpose.CANCEL)

    @extend_schema(methods=["GET"], responses={400: OpenApiTypes.OBJECT}, request=None)
    @extend_schema(methods=["POST"], request=OrderActionIdentitySerializer, responses=ORDER_ACTION_RESPONSES)
    @action(detail=True, methods=["get", "post"], url_path="cancel/message")
    def cancel_message(self, request, uuid=None):
        if request.method == "GET":
            raise OrderActionRefreshRequiredException()
        serializer = OrderActionIdentitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = issue_order_action(request.user, uuid, OrderActionPurpose.CANCEL, serializer.validated_data)
        return Response(action_snapshot(result.action, result.challenge), status=result.http_status)

    @extend_schema(
        parameters=[OpenApiParameter("owner_account_uuid", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True)],
        responses=OrderActionContextSerializer,
    )
    @action(detail=True, methods=["get"], url_path="action-context")
    def action_context(self, request, uuid=None):
        serializer = OrderActionLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(order_action_context(request.user, serializer.validated_data["owner_account_uuid"], uuid))

    @extend_schema(
        parameters=[
            OpenApiParameter("action_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
            OpenApiParameter("owner_account_uuid", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
        ],
        responses=OrderActionSubmissionSerializer,
    )
    @action(detail=False, methods=["get"], url_path=r"actions/(?P<action_id>[^/.]+)")
    def order_action(self, request, action_id=None):
        serializer = OrderActionLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            key = UUID(action_id)
        except (ValueError, TypeError, AttributeError):
            raise NotFound("Order action not found.")
        result = recover_order_action(request.user, serializer.validated_data["owner_account_uuid"], key)
        return Response(action_snapshot(result.action))

    def _execute_action(self, request, order_id, purpose):
        serializer = OrderActionIdentitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = execute_order_action(
            request.user,
            order_id,
            purpose,
            serializer.validated_data,
            request.data,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response(action_snapshot(result.action), status=result.http_status)

    @extend_schema(
        responses={
            200: OrderSubmissionSerializer,
            400: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Invalid request or new-order eligibility."),
            401: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Authentication required."),
            404: OpenApiResponse(response=OpenApiTypes.OBJECT, description="No currently authorized submission."),
            409: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Original submission terms conflict."),
            429: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Request throttle exceeded."),
            503: OpenApiResponse(
                response=OpenApiTypes.OBJECT, description="Service failure; retain the submission ID."
            ),
        }
    )
    @action(detail=False, methods=["post"], url_path="create/message")
    def create_message(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = issue_order_submission(request.user, serializer.validated_data)
        return Response(submission_snapshot(result.submission, result.challenge))

    @extend_schema(
        parameters=[
            OpenApiParameter("submission_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
            OpenApiParameter("owner_account_uuid", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
        ],
        responses={
            200: OrderSubmissionSerializer,
            400: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Invalid account selector."),
            401: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Authentication required."),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT, description="Unknown or currently inaccessible submission."
            ),
            429: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Request throttle exceeded."),
            503: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Service temporarily unavailable."),
        },
    )
    @action(detail=False, methods=["get"], url_path=r"submissions/(?P<submission_id>[^/.]+)")
    def submission(self, request, submission_id=None):
        serializer = OrderSubmissionLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            key = UUID(submission_id)
        except (ValueError, TypeError, AttributeError):
            raise NotFound("Order submission not found.")
        result = recover_order_submission(request.user, serializer.validated_data["owner_account_uuid"], key)
        return Response(submission_snapshot(result.submission))

    @extend_schema(
        responses=inline_serializer(
            name="SwapOrderForSigning",
            fields={
                "swap_order": SwapOrderDetailSerializer(),
                "typed_data": serializers.JSONField(),
                "user_role": serializers.CharField(),
                "has_signed": serializers.BooleanField(),
                "can_sign": serializers.BooleanField(required=False),
                "admission_refusal": serializers.CharField(allow_null=True, required=False),
                "order_uuid": serializers.UUIDField(required=False),
                "owner_account_uuid": serializers.UUIDField(required=False),
                "wallet_uuid": serializers.UUIDField(required=False),
                "swap_uuid": serializers.UUIDField(required=False),
                "settlement_digest": serializers.CharField(required=False),
            },
        )
    )
    @action(detail=True, methods=["get"], url_path="swap")
    def swap(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, has_signed = self._get_authorized_swap_context(request)

        if swap_order.is_expired and not swap_order.settlement_protocol_version:
            raise SwapExpiredException()

        typed_data = atomic_swap_service.get_typed_data(swap_order)

        result = {
            "swap_order": SwapOrderDetailSerializer(swap_order).data,
            "typed_data": typed_data,
            "user_role": user_role,
            "has_signed": has_signed,
        }
        if swap_order.settlement_protocol_version:
            refusal = None
            try:
                require_pending_settlement(swap_order)
            except (SettlementContextChanged, SwapExpiredException, SwapNotReadyException) as exc:
                refusal = exc.default_code
            result.update(self._settlement_echo(request, swap_order, user_role))
            result.update(can_sign=refusal is None and not has_signed, admission_refusal=refusal)
        return Response(result)

    @extend_schema(
        request=SwapSignatureRequestSerializer,
        responses=SwapOrderDetailSerializer,
    )
    @action(detail=True, methods=["post"], url_path="swap/sign")
    def swap_sign(self, request, uuid=None):
        identity = self._settlement_identity(request, write=True)
        if identity is not None:
            atomic_swap_service, swap_order, _role, _signed = self._get_authorized_swap_context(request)
            serializer = SettlementSignatureSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            updated = sign_and_execute_swap(
                atomic_swap_service,
                swap_order=swap_order,
                signature=serializer.validated_data["signature"],
                signer_address=serializer.validated_data["signer_address"],
                admission=self._settlement_admission(request, identity),
            )
            return Response(SwapOrderDetailSerializer(updated).data)
        transfer_order = self.get_object()

        atomic_swap_service = AtomicSwapService()

        swap_order = atomic_swap_service.find_swap_order_by_transfer_order(transfer_order)
        if not swap_order:
            raise NotFound("No swap order found for this transfer order.")
        if swap_order.settlement_protocol_version:
            raise SettlementContextRequired()

        serializer = SubmitSignatureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        signature = serializer.validated_data["signature"]
        signer_address = serializer.validated_data["signer_address"]

        updated_order = sign_and_execute_swap(
            atomic_swap_service,
            swap_order=swap_order,
            signature=signature,
            signer_address=signer_address,
        )

        return Response(SwapOrderDetailSerializer(updated_order).data)

    @extend_schema(
        responses=PolymorphicProxySerializer(
            component_name="SwapApprovalStatus",
            serializers=[ApprovalStatusResponseSerializer, SettlementApprovalStatusSerializer],
            resource_type_field_name=None,
        )
    )
    @action(detail=True, methods=["get"], url_path="swap/approval-status")
    def swap_approval_status(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, _has_signed = self._get_authorized_swap_context(request)
        if swap_order.settlement_protocol_version:
            require_pending_settlement(swap_order)
        user_allowance = atomic_swap_service.check_swap_allowances(swap_order)[user_role]
        result = {
            "swap_uuid": str(swap_order.uuid),
            "user_role": user_role,
            "token_address": user_allowance["token"],
            "token_symbol": user_allowance["token_symbol"],
            "required_amount": user_allowance["required_amount"],
            "current_allowance": user_allowance["current_allowance"],
            "needs_approval": not user_allowance["has_sufficient_allowance"],
            "spender": atomic_swap_service.settlement_contract(swap_order),
        }
        if swap_order.settlement_protocol_version:
            require_pending_settlement(self._settlement_admission(request)(swap_order))
            result.update(self._settlement_echo(request, swap_order, user_role))
            result["required_amount"] = str(result["required_amount"])
            result["current_allowance"] = str(result["current_allowance"])
        return Response(result)

    @extend_schema(responses=ApprovalDataResponseSerializer)
    @action(detail=True, methods=["get"], url_path="swap/approval-data")
    def swap_approval_data(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, _has_signed = self._get_authorized_swap_context(request)
        if swap_order.settlement_protocol_version:
            require_pending_settlement(swap_order)
        user_allowance = atomic_swap_service.check_swap_allowances(swap_order)[user_role]

        if user_allowance["has_sufficient_allowance"]:
            result = {
                "needs_approval": False,
                "message": "User already has sufficient allowance",
                "current_allowance": user_allowance["current_allowance"],
                "required_amount": user_allowance["required_amount"],
            }
            if swap_order.settlement_protocol_version:
                require_pending_settlement(self._settlement_admission(request)(swap_order))
                result.update(self._settlement_echo(request, swap_order, user_role))
                result["required_amount"] = str(result["required_amount"])
                result["current_allowance"] = str(result["current_allowance"])
            return Response(result)

        approval_data = atomic_swap_service.get_approval_transaction_data(
            swap_order=swap_order,
            user_role=user_role,
            unlimited=True,
        )

        result = {
            "needs_approval": True,
            "swap_uuid": str(swap_order.uuid),
            "user_role": user_role,
            **approval_data,
        }
        if swap_order.settlement_protocol_version:
            require_pending_settlement(self._settlement_admission(request)(swap_order))
            result.update(self._settlement_echo(request, swap_order, user_role))
        return Response(result)

    @extend_schema(
        request=SettlementApprovalBroadcastSerializer,
        responses={200: SettlementApprovalReceiptSerializer, 503: SettlementApprovalUncertainSerializer},
    )
    @action(detail=True, methods=["post"], url_path="swap/approval-broadcast")
    def swap_approval_broadcast(self, request, uuid=None):
        serializer = SettlementApprovalBroadcastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identity = serializer.validated_data
        admission = self._settlement_admission(request, identity)
        swap, role, _signed = resolve_exact_swap_context(request.user, uuid, identity)
        service = AtomicSwapService()
        try:
            tx_hash, receipt = service.broadcast_settlement_approval(
                swap, role, identity["signed_transaction"], admission
            )
        except SettlementApprovalUncertain as exc:
            return Response(
                {
                    **self._settlement_echo(request, swap, role),
                    "tx_hash": exc.tx_hash,
                    "code": "swap_approval_unconfirmed",
                    "detail": "Approval outcome remains unconfirmed. Check the original transaction before continuing.",
                },
                status=503,
            )
        return Response(
            {
                **self._settlement_echo(request, swap, role),
                "tx_hash": tx_hash,
                "block_number": receipt.get("blockNumber"),
                "gas_used": receipt.get("gasUsed"),
            }
        )

    def _settlement_identity(self, request, write=False):
        data = request.query_params if request.method == "GET" else request.data
        if not any(key in data for key in ("swap_uuid", "owner_account_uuid", "wallet_uuid", "settlement_digest")):
            return None
        serializer = (SettlementWriteIdentitySerializer if write else SettlementIdentitySerializer)(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _settlement_admission(self, request, identity=None):
        identity = identity or self._settlement_identity(request, write=True)
        order_id = self.kwargs["uuid"]
        return lambda snapshot: resolve_exact_swap_context(request.user, order_id, identity, snapshot)[0]

    def _settlement_echo(self, request, swap, role):
        identity = self._settlement_identity(request)
        return {
            "swap_uuid": str(swap.pk),
            "order_uuid": str(self.kwargs["uuid"]),
            "owner_account_uuid": str(identity["owner_account_uuid"]),
            "wallet_uuid": str(identity["wallet_uuid"]),
            "settlement_digest": swap.settlement_digest,
            "user_role": role,
        }

    def _get_authorized_swap_context(self, request):
        identity = self._settlement_identity(request, write=self.action != "swap")
        if identity is not None:
            swap, role, signed = resolve_exact_swap_context(request.user, self.kwargs["uuid"], identity)
            return AtomicSwapService(), swap, role, signed
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])
        transfer_order = self.get_object()

        swap_order, user_role, has_signed = resolve_order_swap_context(transfer_order, authorized_wallets)
        if swap_order.settlement_protocol_version:
            raise SettlementContextRequired()

        atomic_swap_service = AtomicSwapService()
        return atomic_swap_service, swap_order, user_role, has_signed

    @extend_schema(request=OrderActionModifyRequestSerializer, responses=ORDER_ACTION_RESPONSES)
    @action(detail=True, methods=["post"], url_path="modify/message")
    def modify_message(self, request, uuid=None):
        serializer = OrderActionModifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = issue_order_action(request.user, uuid, OrderActionPurpose.MODIFY, serializer.validated_data)
        return Response(action_snapshot(result.action, result.challenge), status=result.http_status)

    @extend_schema(request=OrderActionExecuteRequestSerializer, responses=ORDER_ACTION_RESPONSES)
    @action(detail=True, methods=["post"], url_path="modify")
    def modify(self, request, uuid=None):
        return self._execute_action(request, uuid, OrderActionPurpose.MODIFY)

    @action(detail=True, methods=["get"], url_path="modifications")
    def modifications(self, request, uuid=None):
        order = self.get_object()
        return Response(get_modification_history(order))
