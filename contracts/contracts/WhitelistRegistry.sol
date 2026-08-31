// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

contract WhitelistRegistry is Ownable, Pausable {
    mapping(address => bool) public whitelisted;
    mapping(address => uint256) public kycTimestamp;
    uint256 public whitelistCount;

    event AddedToWhitelist(address indexed investor, uint256 timestamp);
    event RemovedFromWhitelist(address indexed investor, uint256 timestamp);

    error AlreadyWhitelisted(address investor);
    error NotWhitelisted(address investor);
    error InvalidAddress();

    constructor(address initialOwner) Ownable(initialOwner) {}

    function addToWhitelist(address investor) external onlyOwner whenNotPaused {
        if (investor == address(0)) revert InvalidAddress();
        if (whitelisted[investor]) revert AlreadyWhitelisted(investor);

        whitelisted[investor] = true;
        kycTimestamp[investor] = block.timestamp;
        whitelistCount++;

        emit AddedToWhitelist(investor, block.timestamp);
    }

    function batchAddToWhitelist(address[] calldata investors) external onlyOwner whenNotPaused {
        for (uint256 i = 0; i < investors.length; i++) {
            address investor = investors[i];

            if (investor == address(0)) continue;
            if (whitelisted[investor]) continue;

            whitelisted[investor] = true;
            kycTimestamp[investor] = block.timestamp;
            whitelistCount++;

            emit AddedToWhitelist(investor, block.timestamp);
        }
    }

    function removeFromWhitelist(address investor) external onlyOwner whenNotPaused {
        if (!whitelisted[investor]) revert NotWhitelisted(investor);

        whitelisted[investor] = false;
        kycTimestamp[investor] = 0;
        whitelistCount--;

        emit RemovedFromWhitelist(investor, block.timestamp);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function isWhitelisted(address investor) external view returns (bool) {
        return whitelisted[investor];
    }

    function getInvestorInfo(address investor) external view returns (bool _whitelisted, uint256 _kycTimestamp) {
        return (whitelisted[investor], kycTimestamp[investor]);
    }

    function canReceive(address investor) external view returns (bool) {
        return whitelisted[investor];
    }
}
