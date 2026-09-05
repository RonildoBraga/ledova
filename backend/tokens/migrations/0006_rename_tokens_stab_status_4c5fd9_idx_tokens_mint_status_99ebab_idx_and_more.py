import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0002_alter_blockchaintransaction_tx_type"),
        ("tokens", "0005_rename_token_issuance_to_share_issuance"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="mintrequest",
            new_name="tokens_mint_status_99ebab_idx",
            old_name="tokens_stab_status_4c5fd9_idx",
        ),
        migrations.RenameIndex(
            model_name="mintrequest",
            new_name="tokens_mint_deposit_d00e57_idx",
            old_name="tokens_stab_deposit_7fc908_idx",
        ),
        migrations.RenameIndex(
            model_name="mintrequest",
            new_name="tokens_mint_recipie_c3a7c5_idx",
            old_name="tokens_stab_recipie_dc716d_idx",
        ),
        migrations.RenameIndex(
            model_name="shareissuance",
            new_name="tokens_shar_token_i_02da62_idx",
            old_name="tokens_toke_token_i_b76d43_idx",
        ),
        migrations.RenameIndex(
            model_name="shareissuance",
            new_name="tokens_shar_recipie_43e93e_idx",
            old_name="tokens_toke_recipie_783be6_idx",
        ),
        migrations.RenameIndex(
            model_name="shareissuance",
            new_name="tokens_shar_tx_hash_e61cbd_idx",
            old_name="tokens_toke_tx_hash_27ba2b_idx",
        ),
        migrations.AlterField(
            model_name="capitalincreaserequest",
            name="executed_issuance",
            field=models.OneToOneField(
                blank=True,
                help_text="The executed ShareIssuance record for the minted shares",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="capital_increase",
                to="tokens.shareissuance",
            ),
        ),
        migrations.AlterField(
            model_name="navupdate",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text="Unique identifier (primary key)",
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="shareissuance",
            name="transaction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="share_issuances",
                to="blockchain.blockchaintransaction",
            ),
        ),
        migrations.AlterField(
            model_name="yieldtoken",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text="Unique identifier (primary key)",
                primary_key=True,
                serialize=False,
            ),
        ),
    ]
