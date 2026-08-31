import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.utils import LoggingContext
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.exceptions import (
    OrderModificationException,
    SwapExpiredException,
    SwapOrderNotFoundException,
    SwapSignatureException,
    TokenBalanceRetrievalException,
)
from tokens.filters import TransferOrderFilter
from tokens.models import TransferOrder
from tokens.serializers import (
    OrderModificationExecuteSerializer,
    OrderModificationRequestSerializer,
    TransferOrderCreateSerializer,
    TransferOrderDetailSerializer,
    TransferOrderListSerializer,
)
from tokens.serializers.swap_order import (
    SubmitSignatureSerializer,
    SwapOrderDetailSerializer,
)
from tokens.services import (
    AtomicSwapService,
    OrderModificationService,
    TradingOrderService,
    TransferService,
)

logger = logging.getLogger(__name__)


class TradingOrderViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = TransferOrderListSerializer
    filterset_class = TransferOrderFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "order_type"]
    throttle_scope = "order_write"

    def get_queryset(self):
        return TransferOrder.objects.with_relations()

    def get_serializer_class(self):
        if self.action == "create_order":
            return TransferOrderCreateSerializer
        if self.action in ["retrieve", "cancel"]:
            return TransferOrderDetailSerializer
        return TransferOrderListSerializer

    @action(detail=False, methods=["post"], url_path="create")
    def create_order(self, request):
        serializer = TransferOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        TradingOrderService.verify_order_create_signature(
            wallet_address=data["wallet_address"],
            token_uuid=str(data["token"].uuid),
            order_type=data["order_type"],
            quantity=data["quantity"],
            price_per_share=data["price_per_share"],
            message=request.data.get("message"),
            signature=request.data.get("signature"),
        )

        transfer_service = TransferService()
        order, match_result = transfer_service.create_order_and_match(
            token=data["token"],
            order_type=data["order_type"],
            wallet_address=data["wallet_address"],
            quantity=data["quantity"],
            price_per_share=data["price_per_share"],
            min_quantity=data.get("min_quantity", 0),
        )

        response_data = TradingOrderService.build_order_response(order, match_result)

        logger.info(f"{LoggingContext.ORDER_CREATE} Created {order.order_type} order: {order.uuid}")

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        order = get_object_or_404(TransferOrder, uuid=uuid)

        TradingOrderService.verify_order_cancel_signature(
            order=order,
            message=request.data.get("message"),
            signature=request.data.get("signature"),
        )

        order = TradingOrderService.cancel_order(order)

        return Response(TransferOrderDetailSerializer(order).data)

    @action(detail=True, methods=["get"], url_path="cancel/message")
    def cancel_message(self, request, uuid=None):
        order = get_object_or_404(TransferOrder, uuid=uuid)
        message_data = TradingOrderService.get_order_cancel_message(order)
        return Response(message_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="create/message")
    def create_message(self, request):
        serializer = TransferOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        message_data = TradingOrderService.get_order_create_message(
            wallet_address=data["wallet_address"],
            token_uuid=str(data["token"].uuid),
            order_type=data["order_type"],
            quantity=data["quantity"],
            price_per_share=data["price_per_share"],
        )

        return Response(message_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="swap")
    def swap(self, request, uuid=None):
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        transfer_order = get_object_or_404(TransferOrder, uuid=uuid)

        atomic_swap_service = AtomicSwapService()

        swap_order = atomic_swap_service.find_swap_order_by_transfer_order(transfer_order)
        if not swap_order:
            raise SwapOrderNotFoundException("No swap order found for this transfer order.")

        role_info = atomic_swap_service.determine_user_role(swap_order, wallet_address)
        user_role = role_info["role"]
        has_signed = role_info["has_signed"]

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

    @action(detail=True, methods=["post"], url_path="swap/sign")
    def swap_sign(self, request, uuid=None):
        transfer_order = get_object_or_404(TransferOrder, uuid=uuid)

        atomic_swap_service = AtomicSwapService()

        swap_order = atomic_swap_service.find_swap_order_by_transfer_order(transfer_order)
        if not swap_order:
            raise SwapOrderNotFoundException("No swap order found for this transfer order.")

        serializer = SubmitSignatureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        signature = serializer.validated_data["signature"]
        signer_address = serializer.validated_data["signer_address"]

        try:
            updated_order = atomic_swap_service.submit_signature(
                swap_order=swap_order,
                signature=signature,
                signer_address=signer_address,
            )
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_TRANSFER} Signature submission failed: {e}")
            raise SwapSignatureException(str(e))

        return Response(SwapOrderDetailSerializer(updated_order).data)

    @action(detail=True, methods=["get"], url_path="swap/approval-status")
    def swap_approval_status(self, request, uuid=None):
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        transfer_order = get_object_or_404(TransferOrder, uuid=uuid)

        atomic_swap_service = AtomicSwapService()

        swap_order = atomic_swap_service.find_swap_order_by_transfer_order(transfer_order)
        if not swap_order:
            raise SwapOrderNotFoundException("No swap order found for this transfer order.")

        role_info = atomic_swap_service.determine_user_role(swap_order, wallet_address)
        user_role = role_info["role"]

        try:
            allowances = atomic_swap_service.check_swap_allowances(swap_order)
        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_TRANSFER} Failed to check allowances: {e}")
            raise TokenBalanceRetrievalException()

        user_allowance = allowances[user_role]

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
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        transfer_order = get_object_or_404(TransferOrder, uuid=uuid)

        atomic_swap_service = AtomicSwapService()

        swap_order = atomic_swap_service.find_swap_order_by_transfer_order(transfer_order)
        if not swap_order:
            raise SwapOrderNotFoundException("No swap order found for this transfer order.")

        role_info = atomic_swap_service.determine_user_role(swap_order, wallet_address)
        user_role = role_info["role"]

        try:
            allowances = atomic_swap_service.check_swap_allowances(swap_order)
            user_allowance = allowances[user_role]

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

        except Exception as e:
            logger.error(f"{LoggingContext.TOKEN_TRANSFER} Failed to get approval data: {e}")
            raise TokenBalanceRetrievalException()

    @action(detail=True, methods=["post"], url_path="modify/message")
    def modify_message(self, request, uuid=None):
        order = get_object_or_404(TransferOrder, uuid=uuid)

        serializer = OrderModificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        modification_service = OrderModificationService()

        try:
            result = modification_service.generate_modification_message(
                order=order,
                new_quantity=data.get("new_quantity"),
                new_min_quantity=data.get("new_min_quantity"),
                new_price=data.get("new_price_per_share"),
            )
        except OrderModificationException:
            raise
        except Exception as e:
            raise ValidationError({"error": str(e)})

        logger.info(f"{LoggingContext.ORDER} Generated modification message for order: {order.uuid}")

        return Response(result)

    @action(detail=True, methods=["post"], url_path="modify")
    def modify(self, request, uuid=None):
        order = get_object_or_404(TransferOrder, uuid=uuid)

        serializer = OrderModificationExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        signature = serializer.validated_data["signature"]

        modification_service = OrderModificationService()

        try:
            modified_order, changes = modification_service.apply_modification(
                order=order,
                message=message,
                signature=signature,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except OrderModificationException:
            raise
        except Exception as e:
            logger.error(f"{LoggingContext.ORDER} Order modification failed: {e}")
            raise OrderModificationException("Modification failed due to an internal error")

        match_result = modification_service.check_for_matches_after_modification(modified_order)

        return Response(
            {
                "order": TransferOrderDetailSerializer(modified_order).data,
                "modification_count": modified_order.modification_count,
                "changes": changes,
                "match_found": match_result is not None,
                "match_details": match_result,
            }
        )

    @action(detail=True, methods=["get"], url_path="modifications")
    def modifications(self, request, uuid=None):
        order = get_object_or_404(TransferOrder, uuid=uuid)

        modification_service = OrderModificationService()
        result = modification_service.get_modification_history(order)

        return Response(result)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
