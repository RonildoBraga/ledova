// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "./ShareToken.sol";
import "./WhitelistRegistry.sol";

contract ShareTokenFactory is Ownable {
    WhitelistRegistry public immutable whitelist;

    address[] public deployedTokens;
    mapping(string => address) public tokenByIdentifier;
    mapping(address => bool) public isDeployedToken;

    event ShareTokenCreated(address indexed tokenAddress, string identifier, string symbol, uint256 authorizedShares);

    error CompanyAlreadyExists(string identifier);
    error InvalidParameters();

    constructor(address _whitelist, address _owner) Ownable(_owner) {
        if (_whitelist == address(0)) revert InvalidParameters();
        whitelist = WhitelistRegistry(_whitelist);
    }

    function createShareToken(
        string calldata name,
        string calldata symbol,
        string calldata identifier,
        uint256 authorizedShares,
        address tokenOwner
    ) external onlyOwner returns (address tokenAddress) {
        if (bytes(identifier).length == 0) revert InvalidParameters();
        if (tokenByIdentifier[identifier] != address(0)) revert CompanyAlreadyExists(identifier);
        if (tokenOwner == address(0)) revert InvalidParameters();
        if (authorizedShares == 0) revert InvalidParameters();

        ShareToken token = new ShareToken(name, symbol, address(whitelist), authorizedShares, tokenOwner);

        tokenAddress = address(token);
        deployedTokens.push(tokenAddress);
        tokenByIdentifier[identifier] = tokenAddress;
        isDeployedToken[tokenAddress] = true;

        emit ShareTokenCreated(tokenAddress, identifier, symbol, authorizedShares);

        return tokenAddress;
    }

    function getDeployedTokenCount() external view returns (uint256) {
        return deployedTokens.length;
    }

    function getTokenByIdentifier(string calldata identifier) external view returns (address) {
        return tokenByIdentifier[identifier];
    }
}
