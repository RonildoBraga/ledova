import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from shared.utils import LoggingContext, get_client_ip
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.exceptions import SwapExpiredException, TokenBalanceRetrievalException
from tokens.filters import TransferOrderFilter
from tokens.models import SwapOrder, TransferOrder
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
from tokens.trading_wallet_access import resolve_verified_evm_wallets

logger = logging.getLogger(__name__)


class TradingOrderViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = TransferOrderListSerializer
    filterset_class = TransferOrderFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "order_type"]
    throttle_scope = "order_write"

    def get_queryset(self):
        # Scope to the requesting tenant. Without this, retrieve/list are IDORs:
        # any authenticated user could read any order by UUID.
        return TransferOrder.objects.with_relations().visible_to_user(self.request.user)

    def get_serializer_class(self):
        if self.action == "create_order":
            return TransferOrderCreateSerializer
        if self.action in ["retrieve", "cancel"]:
            return TransferOrderDetailSerializer
        return TransferOrderListSerializer

    @action(detail=False, methods=["post"], url_path="create")
    def create_order(self, request):
        serializer = self.get_serializer(data=request.data)
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
            actor=request.user,
            wallet=data["wallet"],
            owner_account=data["owner_account"],
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
        order = self.get_object()

        TradingOrderService.verify_order_cancel_signature(
            order=order,
            message=request.data.get("message"),
            signature=request.data.get("signature"),
        )

        order = TradingOrderService.cancel_order(order)

        return Response(TransferOrderDetailSerializer(order).data)

    @action(detail=True, methods=["get"], url_path="cancel/message")
    def cancel_message(self, request, uuid=None):
        order = self.get_object()
        message_data = TradingOrderService.get_order_cancel_message(order)
        return Response(message_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="create/message")
    def create_message(self, request):
        serializer = self.get_serializer(data=request.data)
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

        updated_order = atomic_swap_service.submit_signature(
            swap_order=swap_order,
            signature=signature,
            signer_address=signer_address,
        )

        return Response(SwapOrderDetailSerializer(updated_order).data)

    @action(detail=True, methods=["get"], url_path="swap/approval-status")
    def swap_approval_status(self, request, uuid=None):
        atomic_swap_service, swap_order, user_role, _has_signed = self._get_authorized_swap_context(request)

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
        atomic_swap_service, swap_order, user_role, _has_signed = self._get_authorized_swap_context(request)

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

    def _get_authorized_swap_context(self, request):
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])
        transfer_order = self.get_object()

        if (
            transfer_order.wallet_id not in authorized_wallets.wallet_ids
            or transfer_order.wallet.user_account_id != transfer_order.owner_account_id
            or transfer_order.wallet.address.casefold() != transfer_order.wallet_address.casefold()
        ):
            raise NotFound("Order not found.")

        swap_order = SwapOrder.objects.for_transfer_order(transfer_order)
        if not swap_order:
            raise NotFound("No swap order found for this transfer order.")

        if (
            swap_order.sell_order_id == transfer_order.pk
            and swap_order.seller_address.casefold() == transfer_order.wallet_address.casefold()
        ):
            user_role = "seller"
            has_signed = swap_order.seller_has_signed
        elif (
            swap_order.buy_order_id == transfer_order.pk
            and swap_order.buyer_address.casefold() == transfer_order.wallet_address.casefold()
        ):
            user_role = "buyer"
            has_signed = swap_order.buyer_has_signed
        else:
            raise NotFound("Order not found.")

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

    @action(detail=True, methods=["post"], url_path="modify")
    def modify(self, request, uuid=None):
        order = self.get_object()

        serializer = OrderModificationExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        signature = serializer.validated_data["signature"]

        modification_service = OrderModificationService()
        modified_order, changes = modification_service.apply_modification(
            order=order,
            message=message,
            signature=signature,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

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
        order = self.get_object()
        return Response(OrderModificationService().get_modification_history(order))
