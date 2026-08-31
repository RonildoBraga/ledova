// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "./WhitelistRegistry.sol";

/**
 * @title AtomicSwap
 * @notice Enables atomic P2P trading of share tokens for stablecoins using EIP-712 signatures
 * @dev Both buyer and seller sign the same swap order off-chain, then a relayer executes atomically
 *
 * Flow:
 * 1. Orders match off-chain (via backend)
 * 2. SwapOrder created with EIP-712 typed data
 * 3. Both parties sign the swap order (via hardware wallet)
 * 4. Backend (relayer) calls executeSwap with both signatures
 * 5. Shares transfer seller→buyer, stablecoins transfer buyer→seller atomically
 */
contract AtomicSwap is EIP712, ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;

    // EIP-712 type hash for SwapOrder
    bytes32 public constant SWAP_ORDER_TYPEHASH =
        keccak256(
            "SwapOrder(address seller,address buyer,address shareToken,address paymentToken,uint256 shareAmount,uint256 paymentAmount,uint256 nonce,uint256 deadline)"
        );

    WhitelistRegistry public immutable whitelist;

    // Track used nonces per address to prevent replay
    mapping(address => mapping(uint256 => bool)) public usedNonces;

    // Approved tokens
    mapping(address => bool) public approvedShareTokens;
    mapping(address => bool) public approvedPaymentTokens;

    // Relayer addresses authorized to execute swaps
    mapping(address => bool) public relayers;

    event SwapExecuted(
        bytes32 indexed orderHash,
        address indexed seller,
        address indexed buyer,
        address shareToken,
        address paymentToken,
        uint256 shareAmount,
        uint256 paymentAmount,
        uint256 nonce
    );
    event ShareTokenApproved(address indexed token, bool approved);
    event PaymentTokenApproved(address indexed token, bool approved);
    event RelayerUpdated(address indexed relayer, bool authorized);

    error TokenNotApproved();
    error PaymentTokenNotApproved();
    error NotWhitelisted(address account);
    error InvalidSignature(address expected, address recovered);
    error OrderExpired();
    error NonceAlreadyUsed(address account, uint256 nonce);
    error InvalidAmount();
    error NotRelayer();
    error SameParty();

    constructor(address _whitelist, address _owner) EIP712("LedovaAtomicSwap", "1") Ownable(_owner) {
        whitelist = WhitelistRegistry(_whitelist);
        relayers[_owner] = true;
    }

    modifier onlyRelayer() {
        if (!relayers[msg.sender]) revert NotRelayer();
        _;
    }

    /**
     * @notice Authorize or revoke a relayer address
     */
    function setRelayer(address relayer, bool authorized) external onlyOwner {
        relayers[relayer] = authorized;
        emit RelayerUpdated(relayer, authorized);
    }

    /**
     * @notice Approve or revoke a share token for trading
     */
    function setShareTokenApproval(address token, bool approved) external onlyOwner {
        approvedShareTokens[token] = approved;
        emit ShareTokenApproved(token, approved);
    }

    /**
     * @notice Approve or revoke a payment token for trading
     */
    function setPaymentTokenApproval(address token, bool approved) external onlyOwner {
        approvedPaymentTokens[token] = approved;
        emit PaymentTokenApproved(token, approved);
    }

    /**
     * @notice Execute an atomic swap with both signatures
     * @dev Both seller and buyer must have signed the same order hash
     * @param seller Address selling shares
     * @param buyer Address buying shares
     * @param shareToken Address of the share token
     * @param paymentToken Address of the payment token (stablecoin)
     * @param shareAmount Amount of shares to transfer
     * @param paymentAmount Amount of payment tokens to transfer
     * @param nonce Unique nonce for replay protection
     * @param deadline Timestamp after which the order expires
     * @param sellerSignature EIP-712 signature from seller
     * @param buyerSignature EIP-712 signature from buyer
     */
    function executeSwap(
        address seller,
        address buyer,
        address shareToken,
        address paymentToken,
        uint256 shareAmount,
        uint256 paymentAmount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata sellerSignature,
        bytes calldata buyerSignature
    ) external nonReentrant onlyRelayer {
        // Validate inputs
        if (seller == buyer) revert SameParty();
        if (shareAmount == 0 || paymentAmount == 0) revert InvalidAmount();
        if (block.timestamp > deadline) revert OrderExpired();
        if (!approvedShareTokens[shareToken]) revert TokenNotApproved();
        if (!approvedPaymentTokens[paymentToken]) revert PaymentTokenNotApproved();
        if (!whitelist.isWhitelisted(seller)) revert NotWhitelisted(seller);
        if (!whitelist.isWhitelisted(buyer)) revert NotWhitelisted(buyer);

        // Check nonces (both parties use the same nonce for this swap)
        if (usedNonces[seller][nonce]) revert NonceAlreadyUsed(seller, nonce);
        if (usedNonces[buyer][nonce]) revert NonceAlreadyUsed(buyer, nonce);

        // Compute order hash
        bytes32 structHash = keccak256(
            abi.encode(
                SWAP_ORDER_TYPEHASH,
                seller,
                buyer,
                shareToken,
                paymentToken,
                shareAmount,
                paymentAmount,
                nonce,
                deadline
            )
        );
        bytes32 orderHash = _hashTypedDataV4(structHash);

        // Verify signatures
        address recoveredSeller = orderHash.recover(sellerSignature);
        if (recoveredSeller != seller) revert InvalidSignature(seller, recoveredSeller);

        address recoveredBuyer = orderHash.recover(buyerSignature);
        if (recoveredBuyer != buyer) revert InvalidSignature(buyer, recoveredBuyer);

        // Mark nonces as used
        usedNonces[seller][nonce] = true;
        usedNonces[buyer][nonce] = true;

        // Execute atomic transfers
        // Seller sends shares to buyer
        IERC20(shareToken).safeTransferFrom(seller, buyer, shareAmount);
        // Buyer sends payment to seller
        IERC20(paymentToken).safeTransferFrom(buyer, seller, paymentAmount);

        emit SwapExecuted(orderHash, seller, buyer, shareToken, paymentToken, shareAmount, paymentAmount, nonce);
    }

    /**
     * @notice Get the EIP-712 domain separator
     * @return The domain separator used for signing
     */
    function getDomainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }

    /**
     * @notice Compute the order hash for a swap order
     * @dev Used by frontend/backend to generate the message for signing
     */
    function getOrderHash(
        address seller,
        address buyer,
        address shareToken,
        address paymentToken,
        uint256 shareAmount,
        uint256 paymentAmount,
        uint256 nonce,
        uint256 deadline
    ) external view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(
                SWAP_ORDER_TYPEHASH,
                seller,
                buyer,
                shareToken,
                paymentToken,
                shareAmount,
                paymentAmount,
                nonce,
                deadline
            )
        );
        return _hashTypedDataV4(structHash);
    }

    /**
     * @notice Get the EIP-712 typed data hash for signing
     * @dev Returns the struct hash before domain separator is applied
     */
    function getStructHash(
        address seller,
        address buyer,
        address shareToken,
        address paymentToken,
        uint256 shareAmount,
        uint256 paymentAmount,
        uint256 nonce,
        uint256 deadline
    ) external pure returns (bytes32) {
        return
            keccak256(
                abi.encode(
                    SWAP_ORDER_TYPEHASH,
                    seller,
                    buyer,
                    shareToken,
                    paymentToken,
                    shareAmount,
                    paymentAmount,
                    nonce,
                    deadline
                )
            );
    }

    /**
     * @notice Check if a nonce has been used by an address
     */
    function isNonceUsed(address account, uint256 nonce) external view returns (bool) {
        return usedNonces[account][nonce];
    }

    /**
     * @notice Get the chain ID used in the domain separator
     */
    function getChainId() external view returns (uint256) {
        return block.chainid;
    }
}
