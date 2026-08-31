// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./WhitelistRegistry.sol";

/**
 * @title AUSG — synthetic yield-token example
 * @notice Experimental ERC-20 used to demonstrate allowlisted transfers, a
 *         synthetic NAV, and redemption-state transitions. It represents no
 *         real bond, reserve, security, or legal ownership interest.
 * @dev Decimals = 6 for NAV precision. NAV is stored in 6-decimal fixed point
 *      (e.g., 1000000 = $1.00, 1005000 = $1.005).
 */
contract AUSG is ERC20, ERC20Pausable, Ownable {
    WhitelistRegistry public immutable whitelist;

    /// @notice NAV per token in 6-decimal fixed point (1000000 = $1.00)
    uint256 public navPerToken;

    /// @notice Timestamp of the last NAV update
    uint256 public lastNavUpdate;

    /// @notice Synthetic reference value in 6-decimal fixed point; not a real reserve
    uint256 public totalReserveValue;

    /// @notice Addresses authorised to mint tokens
    mapping(address => bool) public minters;

    /// @notice Addresses authorised to update the synthetic NAV scenario
    mapping(address => bool) public navUpdaters;

    /// @notice Redemption request
    struct RedemptionRequest {
        address investor;
        uint256 tokenAmount;
        uint256 navAtRedemption;
        uint256 audAmount;
        uint256 requestedAt;
        bool processed;
    }

    /// @notice All redemption requests
    RedemptionRequest[] public redemptionRequests;

    /// @notice Count of pending (unprocessed) redemption requests
    uint256 public pendingRedemptions;

    // Events
    event NAVUpdated(uint256 oldNav, uint256 newNav, uint256 reserveValue, uint256 timestamp);
    event MinterAdded(address indexed minter);
    event MinterRemoved(address indexed minter);
    event NavUpdaterAdded(address indexed updater);
    event NavUpdaterRemoved(address indexed updater);
    event RedemptionRequested(
        uint256 indexed requestId,
        address indexed investor,
        uint256 tokenAmount,
        uint256 audAmount
    );
    event RedemptionProcessed(uint256 indexed requestId, address indexed investor, uint256 audAmount);

    // Errors
    error NotMinter();
    error NotNavUpdater();
    error InvalidAddress();
    error InvalidAmount();
    error InvalidNAV();
    error RecipientNotWhitelisted(address recipient);
    error InvalidWhitelistRegistry();
    error RedemptionAlreadyProcessed();

    constructor(address _whitelist, address _owner) ERC20("AUSG", "AUSG") Ownable(_owner) {
        if (_whitelist == address(0)) revert InvalidWhitelistRegistry();
        whitelist = WhitelistRegistry(_whitelist);
        navPerToken = 1000000; // Initial NAV = $1.00
        lastNavUpdate = block.timestamp;
    }

    modifier onlyMinter() {
        if (!minters[msg.sender]) revert NotMinter();
        _;
    }

    modifier onlyNavUpdater() {
        if (!navUpdaters[msg.sender]) revert NotNavUpdater();
        _;
    }

    // ============================================================
    // Role Management
    // ============================================================

    function addMinter(address minter) external onlyOwner {
        if (minter == address(0)) revert InvalidAddress();
        minters[minter] = true;
        emit MinterAdded(minter);
    }

    function removeMinter(address minter) external onlyOwner {
        minters[minter] = false;
        emit MinterRemoved(minter);
    }

    function addNavUpdater(address updater) external onlyOwner {
        if (updater == address(0)) revert InvalidAddress();
        navUpdaters[updater] = true;
        emit NavUpdaterAdded(updater);
    }

    function removeNavUpdater(address updater) external onlyOwner {
        navUpdaters[updater] = false;
        emit NavUpdaterRemoved(updater);
    }

    // ============================================================
    // NAV Management
    // ============================================================

    /**
     * @notice Update the synthetic NAV per token in a test environment.
     * @param newNavPerToken New NAV in 6-decimal fixed point (e.g., 1005000 = $1.005)
     * @param newReserveValue Synthetic reference value in 6-decimal fixed point
     */
    function updateNAV(uint256 newNavPerToken, uint256 newReserveValue) external onlyNavUpdater {
        if (newNavPerToken == 0) revert InvalidNAV();

        uint256 oldNav = navPerToken;
        navPerToken = newNavPerToken;
        totalReserveValue = newReserveValue;
        lastNavUpdate = block.timestamp;

        emit NAVUpdated(oldNav, newNavPerToken, newReserveValue, block.timestamp);
    }

    // ============================================================
    // Mint and Redeem
    // ============================================================

    /**
     * @notice Mint example AUSG tokens to an allowlisted test address.
     * @param to Test address (must be allowlisted)
     * @param tokenAmount Number of tokens to mint (in 6-decimal units)
     */
    function mint(address to, uint256 tokenAmount) external onlyMinter whenNotPaused {
        if (to == address(0)) revert InvalidAddress();
        if (tokenAmount == 0) revert InvalidAmount();
        if (!whitelist.isWhitelisted(to)) revert RecipientNotWhitelisted(to);

        _mint(to, tokenAmount);
    }

    /**
     * @notice Request redemption of AUSG tokens. Burns tokens immediately,
     *         records a synthetic payout amount at the current NAV.
     * @param tokenAmount Number of tokens to redeem (in 6-decimal units)
     */
    function redeem(uint256 tokenAmount) external whenNotPaused {
        if (tokenAmount == 0) revert InvalidAmount();
        if (balanceOf(msg.sender) < tokenAmount) revert InvalidAmount();

        // Calculate AUD payout at current NAV
        uint256 audAmount = (tokenAmount * navPerToken) / (10 ** decimals());

        // Burn tokens immediately
        _burn(msg.sender, tokenAmount);

        // Queue the redemption
        uint256 requestId = redemptionRequests.length;
        redemptionRequests.push(
            RedemptionRequest({
                investor: msg.sender,
                tokenAmount: tokenAmount,
                navAtRedemption: navPerToken,
                audAmount: audAmount,
                requestedAt: block.timestamp,
                processed: false
            })
        );
        pendingRedemptions++;

        emit RedemptionRequested(requestId, msg.sender, tokenAmount, audAmount);
    }

    /**
     * @notice Mark a redemption as processed (after AUD has been sent off-chain).
     * @param requestId Index of the redemption request
     */
    function processRedemption(uint256 requestId) external onlyOwner {
        RedemptionRequest storage request = redemptionRequests[requestId];
        if (request.processed) revert RedemptionAlreadyProcessed();

        request.processed = true;
        pendingRedemptions--;

        emit RedemptionProcessed(requestId, request.investor, request.audAmount);
    }

    // ============================================================
    // View Functions
    // ============================================================

    /**
     * @notice Get the total number of redemption requests.
     */
    function redemptionRequestCount() external view returns (uint256) {
        return redemptionRequests.length;
    }

    /**
     * @notice Calculate the AUD value of a token amount at current NAV.
     * @param tokenAmount Number of tokens (in 6-decimal units)
     * @return audValue AUD value in 6-decimal fixed point
     */
    function tokenToAud(uint256 tokenAmount) external view returns (uint256) {
        return (tokenAmount * navPerToken) / (10 ** decimals());
    }

    /**
     * @notice Calculate how many tokens a given AUD amount would mint at current NAV.
     * @param audAmount AUD amount in 6-decimal fixed point
     * @return tokenAmount Number of tokens (in 6-decimal units)
     */
    function audToToken(uint256 audAmount) external view returns (uint256) {
        if (navPerToken == 0) return 0;
        return (audAmount * (10 ** decimals())) / navPerToken;
    }

    // ============================================================
    // Transfer Restrictions
    // ============================================================

    function _update(address from, address to, uint256 value) internal override(ERC20, ERC20Pausable) {
        // Allow burns (to == address(0)) without whitelist check
        if (to != address(0)) {
            if (!whitelist.isWhitelisted(to)) revert RecipientNotWhitelisted(to);
        }
        super._update(from, to, value);
    }

    // ============================================================
    // Admin
    // ============================================================

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }
}
