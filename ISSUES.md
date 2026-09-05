# Deferred high-risk work

The open high-risk work deliberately deferred from this experimental
local and testnet release. Every item needs implementation, tests and
independent review before any public multi-user or real-value use, and each one
names where it lives in the code today.

Items closed since the first publication have been removed; git history holds
them.

1. **Signed-intent binding and replay.**
   `tokens/services/atomic_swap_service.py` signs a nonce and deadline per swap,
   but order create, cancel and modify messages
   (`tokens/services/trading_order_service.py`,
   `tokens/services/order_modification_service.py`) are not bound to one
   reviewed action, account, chain, contract, amount, recipient and short
   expiry, and a challenge is not consumed exactly once.

2. **Trading concurrency and idempotency.** `select_for_update` covers matching
   (`tokens/services/transfer_service.py`) and modification, but there are no
   state-machine invariants at the database level, no replay protection and no
   idempotency keys around order and swap creation, cancellation, matching and
   settlement.

3. **On-chain and background-job idempotency, the remainder.** Share-token
   deployment, issuance and capital increases are covered, and `make chain-test`
   proves the flow against a real Hardhat node
   (`tokens/tests/test_chain_integration.py`). Still open:
   - Minting (`tokens/services/mint_service.py`) and the whitelist service
     (`whitelist/services/whitelist.py`).
   - A request left `EXECUTING` before its mint was sent: nothing is recorded to
     resume on, and the sweep only logs it.
   - A capital-increase worker hard-killed during the receipt wait. The claim
     and the recorded hash live in the row lock's transaction and roll back with
     it, so the retry finds the chain cap already raised, refuses with
     `CAP_NOT_RAISED`, and the database cap has to be set by hand.
   - The `pending` nonce the client takes
     (`integrations/base_chain/client.py`). The row lock serialises per
     `ShareToken` only, so two workers sending for different tokens, or a mint
     and a whitelist add, in the same instant can sign the same nonce and one
     send fails with `nonce too low`. The request is marked failed and retried,
     which is safe now that every hash is recorded first.
   - The row lock held across the 120 second receipt wait. A second executor for
     the same token blocks that long on a database connection, and a production
     `idle_in_transaction_session_timeout` or `lock_timeout` would abort it with
     an `OperationalError` the task retries.
   - A "Retry Deployment" while the first job is still queued or running. Both
     send a create, the second reverts `CompanyAlreadyExists` and the token
     stays on the first hash: correct but noisy.
   - An `eth_sendRawTransaction` whose HTTP response is lost after the node
     accepted it. The create sits in the mempool while the token returns to
     draft; a redeploy with the same symbol adopts it by identifier, but editing
     the draft's symbol first orphans the on-chain token.
   - The retryable Procrastinate tasks generally, after crashes, duplicate
     delivery or uncertain RPC responses.

4. **Pending confirmations.** `wallets/tasks/confirmation.py` and
   `blockchain/tasks.py` mark stale transactions failed after 24 hours. There is
   no reconciliation of submitted transactions for replacement, reorgs, timeouts
   or repeated confirmation jobs, and accounting is optimistic.

5. **Company and capital validation.** `companies/models/company.py` and
   `tokens/models/capital_increase.py` do not verify director authority,
   immutable ownership, ACN or ABN validity, authorized-capital limits, issuance
   totals or concurrent capital changes.

6. **Multi-chain balance aggregation.** `wallets/services/sync.py` and the
   holdings queries scope by wallet, not by the wallet's configured chain, so
   same-address balances or symbols can be merged across networks.

7. **Uploads and media.** `documents/` serves uploads through `MEDIA_URL`
   (`ledova_backend/urls.py`, the `static(...)` call) with no authenticated
   download path, no content or rendered-size limits, no malware handling, no
   lifecycle cleanup and no denial-of-service protection.

8. **Provider logs and webhooks.** `integrations/sumsub/webhook.py`,
   `integrations/kycaid/webhook.py`, `integrations/kycaid/crypto_webhook.py` and
   `integrations/alchemy/webhook.py` verify signatures but log body lengths and
   identifiers and have no replay window. Personal data, credentials, signed
   URLs and provider bodies must be kept out of logs and errors.

9. **Dependencies and mobile hardening.** Resolve production dependency
   advisories, review native supply-chain risk, restrict cleartext networking
   (`mobile/app.json` currently enables `usesCleartextTraffic` on Android),
   validate secure-key storage and backups, and test supported device builds.

Trading stays disabled by default (`feature_flags/middleware.py`, the
`trading_enabled` flag) while these are open. That default is containment, not a
substitute for fixing the underlying designs.
