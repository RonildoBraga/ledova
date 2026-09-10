from uuid import UUID

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from shared.utils import get_client_ip
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.exceptions import SwapExpiredException
from tokens.filters import TransferOrderFilter
from tokens.models import OrderSubmissionStatus, TransferOrder
from tokens.serializers import (
    OrderModificationExecuteSerializer,
    OrderModificationRequestSerializer,
    TransferOrderCreateSerializer,
    TransferOrderDetailSerializer,
    TransferOrderListSerializer,
)
from tokens.serializers.order_submission import (
    OrderSubmissionLookupSerializer,
    OrderSubmissionSerializer,
    SignedOrderSubmissionSerializer,
    submission_snapshot,
)
from tokens.serializers.swap_order import (
    SubmitSignatureSerializer,
    SwapOrderDetailSerializer,
)
from tokens.services import (
    AtomicSwapService,
    OrderModificationService,
    TradingOrderService,
)
from tokens.services.atomic_swap_service import sign_and_execute_swap
from tokens.services.trading_order_access import resolve_order_swap_context
from tokens.services.trading_order_cancel import cancel_signed_order
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
        if self.action in ["retrieve", "cancel"]:
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

    @extend_schema(responses=TransferOrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        order = cancel_signed_order(
            order=self.get_object(),
            digest=request.data.get("digest"),
            signature=request.data.get("signature"),
        )

        return Response(TransferOrderDetailSerializer(order).data)

    @action(detail=True, methods=["get"], url_path="cancel/message")
    def cancel_message(self, request, uuid=None):
        order = self.get_object()
        message_data = TradingOrderService.get_order_cancel_message(order)
        return Response(message_data, status=status.HTTP_200_OK)

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
            },
        )
    )
    @action(detail=True, methods=["get"], url_path="swap")
    def swap(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, has_signed = self._get_authorized_swap_context(request)

        if swap_order.is_expired:
            raise SwapExpiredException()

        typed_data = atomic_swap_service.get_typed_data(swap_order)

        return Response(
            {
                "swap_order": SwapOrderDetailSerializer(swap_order).data,
                "typed_data": typed_data,
                "user_role": user_role,
                "has_signed": has_signed,
            }
        )

    @extend_schema(responses=SwapOrderDetailSerializer)
    @action(detail=True, methods=["post"], url_path="swap/sign")
    def swap_sign(self, request, uuid=None):
        transfer_order = self.get_object()

        atomic_swap_service = AtomicSwapService()

        swap_order = atomic_swap_service.find_swap_order_by_transfer_order(transfer_order)
        if not swap_order:
            raise NotFound("No swap order found for this transfer order.")

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

    @action(detail=True, methods=["get"], url_path="swap/approval-status")
    def swap_approval_status(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, _has_signed = self._get_authorized_swap_context(request)

        user_allowance = atomic_swap_service.check_swap_allowances(swap_order)[user_role]

        return Response(
            {
                "swap_uuid": str(swap_order.uuid),
                "user_role": user_role,
                "token_address": user_allowance["token"],
                "token_symbol": user_allowance["token_symbol"],
                "required_amount": user_allowance["required_amount"],
                "current_allowance": user_allowance["current_allowance"],
                "needs_approval": not user_allowance["has_sufficient_allowance"],
                "spender": atomic_swap_service.contract_address,
            }
        )

    @action(detail=True, methods=["get"], url_path="swap/approval-data")
    def swap_approval_data(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, _has_signed = self._get_authorized_swap_context(request)

        user_allowance = atomic_swap_service.check_swap_allowances(swap_order)[user_role]

        if user_allowance["has_sufficient_allowance"]:
            return Response(
                {
                    "needs_approval": False,
                    "message": "User already has sufficient allowance",
                    "current_allowance": user_allowance["current_allowance"],
                    "required_amount": user_allowance["required_amount"],
                }
            )

        approval_data = atomic_swap_service.get_approval_transaction_data(
            swap_order=swap_order,
            user_role=user_role,
            unlimited=True,
        )

        return Response(
            {
                "needs_approval": True,
                "swap_uuid": str(swap_order.uuid),
                "user_role": user_role,
                **approval_data,
            }
        )

    def _get_authorized_swap_context(self, request):
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])
        transfer_order = self.get_object()

        swap_order, user_role, has_signed = resolve_order_swap_context(transfer_order, authorized_wallets)

        atomic_swap_service = AtomicSwapService()
        return atomic_swap_service, swap_order, user_role, has_signed

    @action(detail=True, methods=["post"], url_path="modify/message")
    def modify_message(self, request, uuid=None):
        order = self.get_object()

        serializer = OrderModificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = OrderModificationService().generate_modification_message(
            order=order,
            new_quantity=data.get("new_quantity"),
            new_min_quantity=data.get("new_min_quantity"),
            new_price=data.get("new_price_per_share"),
        )

        return Response(result)

    @extend_schema(
        responses=inline_serializer(
            name="TransferOrderModified",
            fields={
                "order": TransferOrderDetailSerializer(),
                "modification_count": serializers.IntegerField(),
                "changes": serializers.JSONField(),
            },
        )
    )
    @action(detail=True, methods=["post"], url_path="modify")
    def modify(self, request, uuid=None):
        order = self.get_object()

        serializer = OrderModificationExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        digest = serializer.validated_data["digest"]
        signature = serializer.validated_data["signature"]

        modified_order, changes = OrderModificationService().apply_modification(
            order=order,
            digest=digest,
            signature=signature,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        return Response(
            {
                "order": TransferOrderDetailSerializer(modified_order).data,
                "modification_count": modified_order.modification_count,
                "changes": changes,
            }
        )

    @action(detail=True, methods=["get"], url_path="modifications")
    def modifications(self, request, uuid=None):
        order = self.get_object()
        return Response(OrderModificationService().get_modification_history(order))
