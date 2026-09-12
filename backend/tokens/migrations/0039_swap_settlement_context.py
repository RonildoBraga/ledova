from django.db import migrations, models

GUARD = """
CREATE FUNCTION tokens_swap_settlement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    seller tokens_transferorder%ROWTYPE;
    buyer tokens_transferorder%ROWTYPE;
    context jsonb;
    typed jsonb;
    message jsonb;
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.settlement_protocol_version <> 0 THEN
            RAISE EXCEPTION 'A recorded swap settlement identity cannot be deleted' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.settlement_protocol_version, NEW.settlement_context, NEW.settlement_digest)
           IS DISTINCT FROM ROW(OLD.settlement_protocol_version, OLD.settlement_context, OLD.settlement_digest) THEN
            RAISE EXCEPTION 'A swap cannot replace its original settlement context' USING ERRCODE = '23514';
        END IF;
        IF OLD.settlement_protocol_version <> 0 AND
           ROW(NEW.uuid, NEW.sell_order_id, NEW.buy_order_id, NEW.seller_wallet_id, NEW.buyer_wallet_id,
               NEW.share_token_id, NEW.payment_asset_id, NEW.seller_address, NEW.buyer_address,
               NEW.share_amount, NEW.payment_amount, NEW.nonce, NEW.order_hash, NEW.expires_at, NEW.created_at)
           IS DISTINCT FROM
           ROW(OLD.uuid, OLD.sell_order_id, OLD.buy_order_id, OLD.seller_wallet_id, OLD.buyer_wallet_id,
               OLD.share_token_id, OLD.payment_asset_id, OLD.seller_address, OLD.buyer_address,
               OLD.share_amount, OLD.payment_amount, OLD.nonce, OLD.order_hash, OLD.expires_at, OLD.created_at) THEN
            RAISE EXCEPTION 'A swap settlement identity is immutable' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.settlement_protocol_version IS DISTINCT FROM 1
       OR jsonb_typeof(NEW.settlement_context) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'New swaps require the settlement context protocol' USING ERRCODE = '23514';
    END IF;
    context := NEW.settlement_context;
    typed := context->'typed_data';
    message := typed->'message';
    SELECT * INTO seller FROM tokens_transferorder WHERE uuid = NEW.sell_order_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A swap settlement must name its seller order' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO buyer FROM tokens_transferorder WHERE uuid = NEW.buy_order_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A swap settlement must name its buyer order' USING ERRCODE = '23514';
    END IF;
    IF context->>'protocol_version' IS DISTINCT FROM '1'
       OR seller.token_id IS DISTINCT FROM NEW.share_token_id
       OR buyer.token_id IS DISTINCT FROM NEW.share_token_id
       OR COALESCE(buyer.payment_asset_id, seller.payment_asset_id) IS DISTINCT FROM NEW.payment_asset_id
       OR context->'seller'->>'payment_asset_uuid' IS DISTINCT FROM seller.payment_asset_id::text
       OR context->'buyer'->>'payment_asset_uuid' IS DISTINCT FROM buyer.payment_asset_id::text
       OR seller.order_type IS DISTINCT FROM 'sell'
       OR buyer.order_type IS DISTINCT FROM 'buy'
       OR seller.wallet_id IS DISTINCT FROM NEW.seller_wallet_id
       OR buyer.wallet_id IS DISTINCT FROM NEW.buyer_wallet_id
       OR lower(seller.wallet_address) IS DISTINCT FROM lower(NEW.seller_address)
       OR lower(buyer.wallet_address) IS DISTINCT FROM lower(NEW.buyer_address)
       OR context->>'swap_uuid' IS DISTINCT FROM NEW.uuid::text
       OR context->'seller'->>'order_uuid' IS DISTINCT FROM NEW.sell_order_id::text
       OR context->'buyer'->>'order_uuid' IS DISTINCT FROM NEW.buy_order_id::text
       OR context->'seller'->>'wallet_uuid' IS DISTINCT FROM NEW.seller_wallet_id::text
       OR context->'buyer'->>'wallet_uuid' IS DISTINCT FROM NEW.buyer_wallet_id::text
       OR context->'seller'->>'owner_account_uuid' IS DISTINCT FROM seller.owner_account_id::text
       OR context->'buyer'->>'owner_account_uuid' IS DISTINCT FROM buyer.owner_account_id::text
       OR context->'share_token'->>'uuid' IS DISTINCT FROM NEW.share_token_id::text
       OR context->'payment_asset'->>'uuid' IS DISTINCT FROM NEW.payment_asset_id::text
       OR lower(context->'seller'->>'address') IS DISTINCT FROM lower(NEW.seller_address)
       OR lower(context->'buyer'->>'address') IS DISTINCT FROM lower(NEW.buyer_address)
       OR lower(message->>'seller') IS DISTINCT FROM lower(NEW.seller_address)
       OR lower(message->>'buyer') IS DISTINCT FROM lower(NEW.buyer_address)
       OR message->>'shareAmount' IS DISTINCT FROM NEW.share_amount::text
       OR message->>'paymentAmount' IS DISTINCT FROM NEW.payment_amount::text
       OR message->>'nonce' IS DISTINCT FROM NEW.nonce::text
       OR message->>'deadline' IS DISTINCT FROM trunc(extract(epoch FROM NEW.expires_at))::bigint::text
       OR message->>'shareToken' IS DISTINCT FROM context->'share_token'->>'address'
       OR message->>'paymentToken' IS DISTINCT FROM context->'payment_asset'->>'deployment_address'
       OR context->>'digest' IS DISTINCT FROM NEW.settlement_digest
       OR context->>'order_hash' IS DISTINCT FROM NEW.order_hash
       OR typed->>'primaryType' IS DISTINCT FROM 'SwapOrder'
       OR typed->'domain'->>'name' IS DISTINCT FROM 'LedovaAtomicSwap'
       OR typed->'domain'->>'version' IS DISTINCT FROM '1'
       OR jsonb_typeof(typed->'domain'->'chainId') IS DISTINCT FROM 'string'
       OR COALESCE(typed->'domain'->>'chainId', '') !~ '^[1-9][0-9]*$'
       OR COALESCE(typed->'domain'->>'verifyingContract', '') !~ '^0x[0-9A-Fa-f]{40}$'
       OR COALESCE(NEW.settlement_digest, '') !~ '^0x[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'A swap settlement must preserve its complete signed and relational identity'
            USING ERRCODE = '23514';
    END IF;
    IF typed->'types' IS DISTINCT FROM '{
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"}
        ],
        "SwapOrder": [
            {"name": "seller", "type": "address"},
            {"name": "buyer", "type": "address"},
            {"name": "shareToken", "type": "address"},
            {"name": "paymentToken", "type": "address"},
            {"name": "shareAmount", "type": "uint256"},
            {"name": "paymentAmount", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"}
        ]
    }'::jsonb THEN
        RAISE EXCEPTION 'A swap settlement must retain the V1 signed field types' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tokens_swap_settlement_guard BEFORE INSERT OR UPDATE OR DELETE ON tokens_swaporder
FOR EACH ROW EXECUTE FUNCTION tokens_swap_settlement_guard();
"""


def protect_context(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(GUARD, params=None)


def unprotect_context(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP TRIGGER tokens_swap_settlement_guard ON tokens_swaporder;"
            "DROP FUNCTION tokens_swap_settlement_guard();"
        )


class Migration(migrations.Migration):
    dependencies = [("tokens", "0038_order_action_submissions")]

    operations = [
        migrations.AddField(
            model_name="swaporder",
            name="settlement_protocol_version",
            field=models.PositiveSmallIntegerField(default=0, db_default=0, editable=False),
        ),
        migrations.AddField(
            model_name="swaporder",
            name="settlement_context",
            field=models.JSONField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="swaporder",
            name="settlement_digest",
            field=models.CharField(max_length=66, blank=True, default="", editable=False),
        ),
        migrations.AlterField(
            model_name="swaporder",
            name="settlement_protocol_version",
            field=models.PositiveSmallIntegerField(default=1, db_default=1, editable=False),
        ),
        migrations.AlterField(
            model_name="swaporder",
            name="order_hash",
            field=models.CharField(
                max_length=66, unique=True, help_text="V1 SwapOrder struct hash, excluding the domain"
            ),
        ),
        migrations.AddConstraint(
            model_name="swaporder",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(settlement_protocol_version=0, settlement_context__isnull=True, settlement_digest="")
                    | models.Q(
                        settlement_protocol_version=1,
                        settlement_context__isnull=False,
                        settlement_digest__regex=r"^0x[0-9a-f]{64}$",
                    )
                ),
                name="swap_order_settlement_context_present",
            ),
        ),
        migrations.RunPython(protect_context, unprotect_context),
    ]
