from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from tokens.models import SigningChallenge, SigningChallengePurpose
from tokens.services.signing_challenge import _purge_one_batch, purge_expired_challenges
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

    def test_each_pass_deletes_no_more_than_its_batch(self):
        for nonce in range(5):
            a_challenge(expires_in=-timedelta(seconds=RETENTION + 60), nonce=nonce + 1)

        with patch("tokens.services.signing_challenge._purge_one_batch", wraps=_purge_one_batch) as one_batch:
            self.assertEqual(purge_expired_challenges(batch=2), 5)

        self.assertEqual([call.args[1] for call in one_batch.call_args_list], [2, 2, 2])
        self.assertEqual(SigningChallenge.objects.count(), 0)

    def test_the_periodic_reports_what_it_removed(self):
        a_challenge(expires_in=-timedelta(seconds=RETENTION + 60))

        self.assertEqual(purge_signing_challenges.func(), {"purged": 1})
        self.assertEqual(SigningChallenge.objects.count(), 0)


@override_settings(SIGNING_CHALLENGE_RETENTION_SECONDS=RETENTION)
class TheSweepDrainsTheBacklogRatherThanOneBatchTest(TransactionTestCase):

    BATCH = 4

    def setUp(self):
        self.stale = [a_challenge(expires_in=-timedelta(seconds=RETENTION + 60), nonce=n) for n in range(1, 11)]

    def test_more_than_one_batch_is_removed_in_a_single_run(self):
        removed = purge_expired_challenges(batch=self.BATCH)

        self.assertEqual(removed, len(self.stale))
        self.assertEqual(SigningChallenge.objects.count(), 0)

    def test_a_single_pass_leaves_the_rest_behind_which_is_what_this_fixes(self):
        self.assertEqual(purge_expired_challenges(batch=self.BATCH, passes=1), self.BATCH)

        self.assertEqual(SigningChallenge.objects.count(), len(self.stale) - self.BATCH)

    def test_the_run_stops_as_soon_as_a_batch_comes_back_short(self):
        with patch("tokens.services.signing_challenge._purge_one_batch", side_effect=[4, 4, 2]) as one_batch:
            removed = purge_expired_challenges(batch=self.BATCH)

        self.assertEqual(removed, 10)
        self.assertEqual(one_batch.call_count, 3)

    def test_each_batch_commits_on_its_own_so_a_later_failure_keeps_the_earlier_deletions(self):
        real = _purge_one_batch
        calls = {"n": 0}

        def fail_on_the_third(cutoff, batch):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("the database went away")
            return real(cutoff, batch)

        with patch("tokens.services.signing_challenge._purge_one_batch", side_effect=fail_on_the_third):
            with self.assertRaises(RuntimeError):
                purge_expired_challenges(batch=self.BATCH)

        self.assertEqual(SigningChallenge.objects.count(), len(self.stale) - 2 * self.BATCH)

    def test_a_backlog_the_run_cannot_finish_is_reported_rather_than_left_silent(self):
        with patch("tokens.services.signing_challenge._purge_one_batch", return_value=self.BATCH):
            with self.assertLogs("tokens.services.signing_challenge", level="WARNING") as logs:
                removed = purge_expired_challenges(batch=self.BATCH, passes=3)

        self.assertEqual(removed, 12)
        self.assertIn("arriving faster than they are swept", logs.output[0])

    def test_a_spent_challenge_survives_however_many_passes_it_takes(self):
        spent = a_challenge(expires_in=-timedelta(seconds=RETENTION + 60), consumed=True, nonce=99)

        purge_expired_challenges(batch=self.BATCH)

        self.assertTrue(SigningChallenge.objects.filter(pk=spent.pk).exists())
