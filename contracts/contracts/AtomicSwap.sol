// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "./WhitelistRegistry.sol";

contract AtomicSwap is EIP712, ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;

    bytes32 public constant SWAP_ORDER_TYPEHASH =
        keccak256(
            "SwapOrder(address seller,address buyer,address shareToken,address paymentToken,uint256 shareAmount,uint256 paymentAmount,uint256 nonce,uint256 deadline)"
        );

    WhitelistRegistry public immutable whitelist;

    mapping(address => mapping(uint256 => bool)) public usedNonces;

    mapping(address => bool) public approvedShareTokens;
    mapping(address => bool) public approvedPaymentTokens;

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

    function setRelayer(address relayer, bool authorized) external onlyOwner {
        relayers[relayer] = authorized;
        emit RelayerUpdated(relayer, authorized);
    }

    function setShareTokenApproval(address token, bool approved) external onlyOwner {
        approvedShareTokens[token] = approved;
        emit ShareTokenApproved(token, approved);
    }

    function setPaymentTokenApproval(address token, bool approved) external onlyOwner {
        approvedPaymentTokens[token] = approved;
        emit PaymentTokenApproved(token, approved);
    }

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

        if (seller == buyer) revert SameParty();
        if (shareAmount == 0 || paymentAmount == 0) revert InvalidAmount();
        if (block.timestamp > deadline) revert OrderExpired();
        if (!approvedShareTokens[shareToken]) revert TokenNotApproved();
        if (!approvedPaymentTokens[paymentToken]) revert PaymentTokenNotApproved();
        if (!whitelist.isWhitelisted(seller)) revert NotWhitelisted(seller);
        if (!whitelist.isWhitelisted(buyer)) revert NotWhitelisted(buyer);

        if (usedNonces[seller][nonce]) revert NonceAlreadyUsed(seller, nonce);
        if (usedNonces[buyer][nonce]) revert NonceAlreadyUsed(buyer, nonce);

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

        address recoveredSeller = orderHash.recover(sellerSignature);
        if (recoveredSeller != seller) revert InvalidSignature(seller, recoveredSeller);

        address recoveredBuyer = orderHash.recover(buyerSignature);
        if (recoveredBuyer != buyer) revert InvalidSignature(buyer, recoveredBuyer);

        usedNonces[seller][nonce] = true;
        usedNonces[buyer][nonce] = true;

        IERC20(shareToken).safeTransferFrom(seller, buyer, shareAmount);

        IERC20(paymentToken).safeTransferFrom(buyer, seller, paymentAmount);

        emit SwapExecuted(orderHash, seller, buyer, shareToken, paymentToken, shareAmount, paymentAmount, nonce);
    }

    function getDomainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }

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

    function isNonceUsed(address account, uint256 nonce) external view returns (bool) {
        return usedNonces[account][nonce];
    }

    function getChainId() external view returns (uint256) {
        return block.chainid;
    }
}
