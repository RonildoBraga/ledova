from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from tokens.models import SigningChallenge, SigningChallengePurpose
from tokens.services.signing_challenge import purge_expired_challenges
from tokens.tasks.signing_challenge import purge_signing_challenges

WALLET = "0x" + "a1" * 20
RETENTION = 3600


def a_challenge(*, expires_in, consumed=False, nonce=1):
    now = timezone.now()
    return SigningChallenge.objects.create(
        purpose=SigningChallengePurpose.ORDER_CANCEL,
        wallet_address=WALLET,
        chain_id=84532,
        verifying_contract="0x" + "b2" * 20,
        payload={"domain": {}, "types": {}, "message": {}},
        digest="0x" + f"{nonce:064x}",
        nonce=nonce,
        expires_at=now + expires_in,
        consumed_at=now if consumed else None,
    )


@override_settings(SIGNING_CHALLENGE_RETENTION_SECONDS=RETENTION)
class ExpiredChallengesArePurgedTest(TestCase):

    def test_an_unspent_challenge_past_the_retention_window_is_purged(self):
        stale = a_challenge(expires_in=-timedelta(seconds=RETENTION + 60))

        self.assertEqual(purge_expired_challenges(), 1)
        self.assertFalse(SigningChallenge.objects.filter(pk=stale.pk).exists())

    def test_an_unspent_challenge_inside_the_retention_window_is_kept(self):
        recent = a_challenge(expires_in=-timedelta(seconds=60))

        self.assertEqual(purge_expired_challenges(), 0)
        self.assertTrue(SigningChallenge.objects.filter(pk=recent.pk).exists())

    def test_a_live_challenge_is_never_purged(self):
        live = a_challenge(expires_in=timedelta(minutes=5))

        self.assertEqual(purge_expired_challenges(), 0)
        self.assertTrue(SigningChallenge.objects.filter(pk=live.pk).exists())

    def test_a_consumed_challenge_is_kept_however_old_it_is(self):
        spent = a_challenge(expires_in=-timedelta(days=365), consumed=True)

        self.assertEqual(purge_expired_challenges(), 0)
        self.assertTrue(SigningChallenge.objects.filter(pk=spent.pk).exists())

    def test_the_sweep_is_bounded_by_its_batch(self):
        for nonce in range(5):
            a_challenge(expires_in=-timedelta(seconds=RETENTION + 60), nonce=nonce + 1)

        self.assertEqual(purge_expired_challenges(batch=2), 2)
        self.assertEqual(SigningChallenge.objects.count(), 3)

    def test_the_periodic_reports_what_it_removed(self):
        a_challenge(expires_in=-timedelta(seconds=RETENTION + 60))

        self.assertEqual(purge_signing_challenges.func(), {"purged": 1})
        self.assertEqual(SigningChallenge.objects.count(), 0)
