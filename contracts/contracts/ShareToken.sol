// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./WhitelistRegistry.sol";

contract ShareToken is ERC20, ERC20Burnable, ERC20Pausable, Ownable {
    WhitelistRegistry public immutable whitelist;
    uint256 public authorizedShares;

    event SharesIssued(address indexed to, uint256 amount);
    event AuthorizedSharesUpdated(uint256 oldAmount, uint256 newAmount);

    error RecipientNotWhitelisted(address recipient);
    error ExceedsAuthorizedShares(uint256 requested, uint256 available);
    error InvalidWhitelistRegistry();

    constructor(
        string memory _name,
        string memory _symbol,
        address _whitelist,
        uint256 _authorizedShares,
        address _owner
    ) ERC20(_name, _symbol) Ownable(_owner) {
        if (_whitelist == address(0)) revert InvalidWhitelistRegistry();
        whitelist = WhitelistRegistry(_whitelist);
        authorizedShares = _authorizedShares;
    }

    function mint(address to, uint256 amount) external onlyOwner whenNotPaused {
        if (!whitelist.isWhitelisted(to)) revert RecipientNotWhitelisted(to);
        if (totalSupply() + amount > authorizedShares)
            revert ExceedsAuthorizedShares(amount, authorizedShares - totalSupply());

        _mint(to, amount);
        emit SharesIssued(to, amount);
    }

    function setAuthorizedShares(uint256 newAmount) external onlyOwner {
        require(newAmount >= totalSupply(), "Cannot reduce below current supply");
        emit AuthorizedSharesUpdated(authorizedShares, newAmount);
        authorizedShares = newAmount;
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function decimals() public pure override returns (uint8) {
        return 0;
    }

    function _update(address from, address to, uint256 value) internal override(ERC20, ERC20Pausable) {
        if (to != address(0)) {
            if (!whitelist.isWhitelisted(to)) revert RecipientNotWhitelisted(to);
        }
        super._update(from, to, value);
    }
}
