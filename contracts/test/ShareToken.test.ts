import { expect } from "chai";
import { ethers } from "hardhat";
import { ShareToken, WhitelistRegistry } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("ShareToken", function () {
  let whitelist: WhitelistRegistry;
  let shareToken: ShareToken;
  let owner: SignerWithAddress;
  let company: SignerWithAddress;
  let investor1: SignerWithAddress;
  let investor2: SignerWithAddress;
  let nonWhitelisted: SignerWithAddress;

  const TOKEN_NAME = "Test Company Shares";
  const TOKEN_SYMBOL = "TEST";
  const AUTHORIZED_SHARES = 1000000n;

  beforeEach(async function () {
    [owner, company, investor1, investor2, nonWhitelisted] =
      await ethers.getSigners();

    const WhitelistRegistry =
      await ethers.getContractFactory("WhitelistRegistry");
    whitelist = await WhitelistRegistry.deploy(owner.address);
    await whitelist.waitForDeployment();

    await whitelist.addToWhitelist(investor1.address);
    await whitelist.addToWhitelist(investor2.address);

    const ShareToken = await ethers.getContractFactory("ShareToken");
    shareToken = await ShareToken.deploy(
      TOKEN_NAME,
      TOKEN_SYMBOL,
      await whitelist.getAddress(),
      AUTHORIZED_SHARES,
      company.address,
    );
    await shareToken.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should set the correct name and symbol", async function () {
      expect(await shareToken.name()).to.equal(TOKEN_NAME);
      expect(await shareToken.symbol()).to.equal(TOKEN_SYMBOL);
    });

    it("Should set the correct owner", async function () {
      expect(await shareToken.owner()).to.equal(company.address);
    });

    it("Should set the correct authorized shares", async function () {
      expect(await shareToken.authorizedShares()).to.equal(AUTHORIZED_SHARES);
    });

    it("Should have zero decimals (whole shares)", async function () {
      expect(await shareToken.decimals()).to.equal(0);
    });

    it("Should start with zero total supply", async function () {
      expect(await shareToken.totalSupply()).to.equal(0);
    });

    it("Should revert if whitelist is zero address", async function () {
      const ShareToken = await ethers.getContractFactory("ShareToken");
      await expect(
        ShareToken.deploy(
          TOKEN_NAME,
          TOKEN_SYMBOL,
          ethers.ZeroAddress,
          AUTHORIZED_SHARES,
          company.address,
        ),
      ).to.be.revertedWithCustomError(shareToken, "InvalidWhitelistRegistry");
    });
  });

  describe("Minting Shares", function () {
    it("Should mint shares to whitelisted investor", async function () {
      const amount = 1000n;

      await expect(shareToken.connect(company).mint(investor1.address, amount))
        .to.emit(shareToken, "SharesIssued")
        .withArgs(investor1.address, amount);

      expect(await shareToken.balanceOf(investor1.address)).to.equal(amount);
      expect(await shareToken.totalSupply()).to.equal(amount);
    });

    it("Should revert when minting to non-whitelisted address", async function () {
      await expect(
        shareToken.connect(company).mint(nonWhitelisted.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "RecipientNotWhitelisted");
    });

    it("Should revert when exceeding authorized shares", async function () {
      await expect(
        shareToken
          .connect(company)
          .mint(investor1.address, AUTHORIZED_SHARES + 1n),
      ).to.be.revertedWithCustomError(shareToken, "ExceedsAuthorizedShares");
    });

    it("Should revert when non-owner tries to mint", async function () {
      await expect(
        shareToken.connect(investor1).mint(investor1.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "OwnableUnauthorizedAccount");
    });
  });

  describe("Transfers", function () {
    beforeEach(async function () {
      await shareToken.connect(company).mint(investor1.address, 10000n);
    });

    it("Should allow transfer between whitelisted addresses", async function () {
      await shareToken.connect(investor1).transfer(investor2.address, 1000n);

      expect(await shareToken.balanceOf(investor1.address)).to.equal(9000n);
      expect(await shareToken.balanceOf(investor2.address)).to.equal(1000n);
    });

    it("Should revert transfer to non-whitelisted address", async function () {
      await expect(
        shareToken.connect(investor1).transfer(nonWhitelisted.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "RecipientNotWhitelisted");
    });

    it("Should allow transferFrom between whitelisted addresses", async function () {
      await shareToken.connect(investor1).approve(investor2.address, 1000n);

      await shareToken
        .connect(investor2)
        .transferFrom(investor1.address, investor2.address, 1000n);

      expect(await shareToken.balanceOf(investor2.address)).to.equal(1000n);
    });

    it("Should revert transferFrom to non-whitelisted address", async function () {
      await shareToken.connect(investor1).approve(investor2.address, 1000n);

      await expect(
        shareToken
          .connect(investor2)
          .transferFrom(investor1.address, nonWhitelisted.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "RecipientNotWhitelisted");
    });
  });

  describe("Burning Shares", function () {
    beforeEach(async function () {
      await shareToken.connect(company).mint(investor1.address, 10000n);
    });

    it("Should allow burning shares", async function () {
      await shareToken.connect(investor1).burn(1000n);

      expect(await shareToken.balanceOf(investor1.address)).to.equal(9000n);
      expect(await shareToken.totalSupply()).to.equal(9000n);
    });
  });

  describe("Authorized Shares", function () {
    it("Should update authorized shares", async function () {
      const newAuthorized = 2000000n;

      await expect(
        shareToken.connect(company).setAuthorizedShares(newAuthorized),
      )
        .to.emit(shareToken, "AuthorizedSharesUpdated")
        .withArgs(AUTHORIZED_SHARES, newAuthorized);

      expect(await shareToken.authorizedShares()).to.equal(newAuthorized);
    });

    it("Should revert if reducing below current supply", async function () {
      await shareToken.connect(company).mint(investor1.address, 500000n);

      await expect(
        shareToken.connect(company).setAuthorizedShares(100000n),
      ).to.be.revertedWith("Cannot reduce below current supply");
    });
  });

  describe("Pause/Unpause", function () {
    beforeEach(async function () {
      await shareToken.connect(company).mint(investor1.address, 10000n);
    });

    it("Should pause transfers", async function () {
      await shareToken.connect(company).pause();

      await expect(
        shareToken.connect(investor1).transfer(investor2.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "EnforcedPause");
    });

    it("Should prevent minting when paused", async function () {
      await shareToken.connect(company).pause();

      await expect(
        shareToken.connect(company).mint(investor1.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "EnforcedPause");
    });

    it("Should allow transfers after unpause", async function () {
      await shareToken.connect(company).pause();
      await shareToken.connect(company).unpause();

      await shareToken.connect(investor1).transfer(investor2.address, 1000n);
      expect(await shareToken.balanceOf(investor2.address)).to.equal(1000n);
    });
  });
});
