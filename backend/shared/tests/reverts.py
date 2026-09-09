from eth_abi import encode
from web3 import Web3

RPC_HOST = "node.example.test"
RPC_KEY = "synthetic-rpc-key"
RPC_URL = f"https://{RPC_HOST}/v2/{RPC_KEY}/0x" + "ab" * 200
ADDRESS = "0x" + "a" * 40


def revert_payload(signature, types=(), values=()):
    return "0x" + Web3.keccak(text=signature)[:4].hex() + encode(types, values).hex()


def actionable_reverts():
    return (
        (revert_payload("NotWhitelisted(address)", ["address"], [ADDRESS]), "Account is not whitelisted"),
        (
            revert_payload("RecipientNotWhitelisted(address)", ["address"], [ADDRESS]),
            "Recipient is not whitelisted for transfers",
        ),
        (revert_payload("OrderExpired()"), "Swap order has expired"),
        (revert_payload("EnforcedPause()"), "Token transfers are paused"),
        (
            revert_payload(
                "ERC20InsufficientAllowance(address,uint256,uint256)",
                ["address", "uint256", "uint256"],
                [ADDRESS, 5, 10],
            ),
            "Insufficient allowance: approved 5 base units but need 10",
        ),
        (
            revert_payload(
                "ERC20InsufficientBalance(address,uint256,uint256)", ["address", "uint256", "uint256"], [ADDRESS, 5, 10]
            ),
            "Insufficient balance: you have 5 base units but need 10",
        ),
    )


def provider_revert(payload):
    return ValueError({"code": -32000, "message": f"execution reverted at {RPC_URL}", "data": payload})
