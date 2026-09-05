// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./WhitelistRegistry.sol";

contract AUSG is ERC20, ERC20Pausable, Ownable {
    WhitelistRegistry public immutable whitelist;

    uint256 public navPerToken;

    uint256 public lastNavUpdate;

    uint256 public totalReserveValue;

    mapping(address => bool) public minters;

    mapping(address => bool) public navUpdaters;

    struct RedemptionRequest {
        address investor;
        uint256 tokenAmount;
        uint256 navAtRedemption;
        uint256 audAmount;
        uint256 requestedAt;
        bool processed;
    }

    RedemptionRequest[] public redemptionRequests;

    uint256 public pendingRedemptions;

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
        navPerToken = 1000000;
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

    function updateNAV(uint256 newNavPerToken, uint256 newReserveValue) external onlyNavUpdater {
        if (newNavPerToken == 0) revert InvalidNAV();

        uint256 oldNav = navPerToken;
        navPerToken = newNavPerToken;
        totalReserveValue = newReserveValue;
        lastNavUpdate = block.timestamp;

        emit NAVUpdated(oldNav, newNavPerToken, newReserveValue, block.timestamp);
    }

    function mint(address to, uint256 tokenAmount) external onlyMinter whenNotPaused {
        if (to == address(0)) revert InvalidAddress();
        if (tokenAmount == 0) revert InvalidAmount();
        if (!whitelist.isWhitelisted(to)) revert RecipientNotWhitelisted(to);

        _mint(to, tokenAmount);
    }

    function redeem(uint256 tokenAmount) external whenNotPaused {
        if (tokenAmount == 0) revert InvalidAmount();
        if (balanceOf(msg.sender) < tokenAmount) revert InvalidAmount();

        uint256 audAmount = (tokenAmount * navPerToken) / (10 ** decimals());

        _burn(msg.sender, tokenAmount);

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

    function processRedemption(uint256 requestId) external onlyOwner {
        RedemptionRequest storage request = redemptionRequests[requestId];
        if (request.processed) revert RedemptionAlreadyProcessed();

        request.processed = true;
        pendingRedemptions--;

        emit RedemptionProcessed(requestId, request.investor, request.audAmount);
    }

    function redemptionRequestCount() external view returns (uint256) {
        return redemptionRequests.length;
    }

    function tokenToAud(uint256 tokenAmount) external view returns (uint256) {
        return (tokenAmount * navPerToken) / (10 ** decimals());
    }

    function audToToken(uint256 audAmount) external view returns (uint256) {
        if (navPerToken == 0) return 0;
        return (audAmount * (10 ** decimals())) / navPerToken;
    }

    function _update(address from, address to, uint256 value) internal override(ERC20, ERC20Pausable) {

        if (to != address(0)) {
            if (!whitelist.isWhitelisted(to)) revert RecipientNotWhitelisted(to);
        }
        super._update(from, to, value);
    }

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
