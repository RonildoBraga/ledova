import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import { AUSG, WhitelistRegistry } from "../typechain-types";

describe("AUSG", function () {
  async function deployFixture() {
    const [owner, minter, navUpdater, investor1, investor2, nonWhitelisted] =
      await ethers.getSigners();

    const WhitelistRegistry =
      await ethers.getContractFactory("WhitelistRegistry");
    const whitelist = await WhitelistRegistry.deploy(owner.address);

    const AUSG = await ethers.getContractFactory("AUSG");
    const ausg = await AUSG.deploy(await whitelist.getAddress(), owner.address);

    await ausg.addMinter(minter.address);
    await ausg.addNavUpdater(navUpdater.address);

    await whitelist.addToWhitelist(investor1.address);
    await whitelist.addToWhitelist(investor2.address);

    return {
      ausg,
      whitelist,
      owner,
      minter,
      navUpdater,
      investor1,
      investor2,
      nonWhitelisted,
    };
  }

  describe("Deployment", function () {
    it("Should set correct name, symbol, and decimals", async function () {
      const { ausg } = await loadFixture(deployFixture);
      expect(await ausg.name()).to.equal("AUSG");
      expect(await ausg.symbol()).to.equal("AUSG");
      expect(await ausg.decimals()).to.equal(6);
    });

    it("Should set initial NAV to $1.00", async function () {
      const { ausg } = await loadFixture(deployFixture);
      expect(await ausg.navPerToken()).to.equal(1000000);
    });

    it("Should set whitelist registry", async function () {
      const { ausg, whitelist } = await loadFixture(deployFixture);
      expect(await ausg.whitelist()).to.equal(await whitelist.getAddress());
    });

    it("Should revert with zero whitelist address", async function () {
      const [, , , , , , validOwner] = await ethers.getSigners();
      const AUSG = await ethers.getContractFactory("AUSG");
      await expect(
        AUSG.deploy(ethers.ZeroAddress, validOwner.address),
      ).to.be.revertedWithCustomError(AUSG, "InvalidWhitelistRegistry");
    });
  });

  describe("Role Management", function () {
    it("Should add and remove minters", async function () {
      const { ausg, owner, investor1 } = await loadFixture(deployFixture);
      await ausg.addMinter(investor1.address);
      expect(await ausg.minters(investor1.address)).to.be.true;
      await ausg.removeMinter(investor1.address);
      expect(await ausg.minters(investor1.address)).to.be.false;
    });

    it("Should add and remove NAV updaters", async function () {
      const { ausg, investor1 } = await loadFixture(deployFixture);
      await ausg.addNavUpdater(investor1.address);
      expect(await ausg.navUpdaters(investor1.address)).to.be.true;
      await ausg.removeNavUpdater(investor1.address);
      expect(await ausg.navUpdaters(investor1.address)).to.be.false;
    });

    it("Should revert when non-owner adds minter", async function () {
      const { ausg, investor1 } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(investor1).addMinter(investor1.address),
      ).to.be.revertedWithCustomError(ausg, "OwnableUnauthorizedAccount");
    });
  });

  describe("NAV Updates", function () {
    it("Should update NAV", async function () {
      const { ausg, navUpdater } = await loadFixture(deployFixture);
      await ausg.connect(navUpdater).updateNAV(1005000, 50000000000);

      expect(await ausg.navPerToken()).to.equal(1005000);
      expect(await ausg.totalReserveValue()).to.equal(50000000000);
    });

    it("Should emit NAVUpdated event", async function () {
      const { ausg, navUpdater } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(navUpdater).updateNAV(1005000, 50000000000),
      ).to.emit(ausg, "NAVUpdated");
    });

    it("Should revert with zero NAV", async function () {
      const { ausg, navUpdater } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(navUpdater).updateNAV(0, 0),
      ).to.be.revertedWithCustomError(ausg, "InvalidNAV");
    });

    it("Should revert when non-updater updates NAV", async function () {
      const { ausg, investor1 } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(investor1).updateNAV(1005000, 0),
      ).to.be.revertedWithCustomError(ausg, "NotNavUpdater");
    });
  });

  describe("Minting", function () {
    it("Should mint tokens to whitelisted investor", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      const amount = 1000000000;

      await ausg.connect(minter).mint(investor1.address, amount);
      expect(await ausg.balanceOf(investor1.address)).to.equal(amount);
    });

    it("Should revert minting to non-whitelisted address", async function () {
      const { ausg, minter, nonWhitelisted } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(minter).mint(nonWhitelisted.address, 1000000),
      ).to.be.revertedWithCustomError(ausg, "RecipientNotWhitelisted");
    });

    it("Should revert when non-minter tries to mint", async function () {
      const { ausg, investor1 } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(investor1).mint(investor1.address, 1000000),
      ).to.be.revertedWithCustomError(ausg, "NotMinter");
    });

    it("Should revert minting zero amount", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      await expect(
        ausg.connect(minter).mint(investor1.address, 0),
      ).to.be.revertedWithCustomError(ausg, "InvalidAmount");
    });
  });

  describe("Redemption", function () {
    it("Should create a redemption request and burn tokens", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      const mintAmount = 1000000000;

      await ausg.connect(minter).mint(investor1.address, mintAmount);
      const redeemAmount = 500000000;

      await ausg.connect(investor1).redeem(redeemAmount);

      expect(await ausg.balanceOf(investor1.address)).to.equal(
        mintAmount - redeemAmount,
      );

      expect(await ausg.redemptionRequestCount()).to.equal(1);
      expect(await ausg.pendingRedemptions()).to.equal(1);

      const request = await ausg.redemptionRequests(0);
      expect(request.investor).to.equal(investor1.address);
      expect(request.tokenAmount).to.equal(redeemAmount);
      expect(request.navAtRedemption).to.equal(1000000);
      expect(request.audAmount).to.equal(500000000);
      expect(request.processed).to.be.false;
    });

    it("Should emit RedemptionRequested event", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000000);

      await expect(ausg.connect(investor1).redeem(500000000))
        .to.emit(ausg, "RedemptionRequested")
        .withArgs(0, investor1.address, 500000000, 500000000);
    });

    it("Should calculate correct AUD amount with updated NAV", async function () {
      const { ausg, minter, navUpdater, investor1 } =
        await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000000);

      await ausg.connect(navUpdater).updateNAV(1005000, 50000000000);

      await ausg.connect(investor1).redeem(1000000000);

      const request = await ausg.redemptionRequests(0);
      expect(request.audAmount).to.equal(1005000000);
    });

    it("Should process a redemption", async function () {
      const { ausg, minter, owner, investor1 } =
        await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000000);
      await ausg.connect(investor1).redeem(500000000);

      await ausg.connect(owner).processRedemption(0);

      const request = await ausg.redemptionRequests(0);
      expect(request.processed).to.be.true;
      expect(await ausg.pendingRedemptions()).to.equal(0);
    });

    it("Should revert processing already processed redemption", async function () {
      const { ausg, minter, owner, investor1 } =
        await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000000);
      await ausg.connect(investor1).redeem(500000000);
      await ausg.connect(owner).processRedemption(0);

      await expect(
        ausg.connect(owner).processRedemption(0),
      ).to.be.revertedWithCustomError(ausg, "RedemptionAlreadyProcessed");
    });

    it("Should revert redeeming more than balance", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000);

      await expect(
        ausg.connect(investor1).redeem(2000000),
      ).to.be.revertedWithCustomError(ausg, "InvalidAmount");
    });
  });

  describe("Transfer Restrictions", function () {
    it("Should allow transfer between whitelisted addresses", async function () {
      const { ausg, minter, investor1, investor2 } =
        await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000);

      await ausg.connect(investor1).transfer(investor2.address, 500000);
      expect(await ausg.balanceOf(investor2.address)).to.equal(500000);
    });

    it("Should reject transfer to non-whitelisted address", async function () {
      const { ausg, minter, investor1, nonWhitelisted } =
        await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000);

      await expect(
        ausg.connect(investor1).transfer(nonWhitelisted.address, 500000),
      ).to.be.revertedWithCustomError(ausg, "RecipientNotWhitelisted");
    });
  });

  describe("View Functions", function () {
    it("Should convert tokens to AUD at current NAV", async function () {
      const { ausg, navUpdater } = await loadFixture(deployFixture);
      await ausg.connect(navUpdater).updateNAV(1005000, 0);

      expect(await ausg.tokenToAud(1000000000)).to.equal(1005000000);
    });

    it("Should convert AUD to tokens at current NAV", async function () {
      const { ausg, navUpdater } = await loadFixture(deployFixture);
      await ausg.connect(navUpdater).updateNAV(1005000, 0);

      expect(await ausg.audToToken(1005000000)).to.equal(1000000000);
    });

    it("Should return 0 tokens for 0 NAV", async function () {
      const { ausg } = await loadFixture(deployFixture);
      expect(await ausg.audToToken(0)).to.equal(0);
    });
  });

  describe("Pause", function () {
    it("Should pause and unpause", async function () {
      const { ausg, owner } = await loadFixture(deployFixture);
      await ausg.pause();
      expect(await ausg.paused()).to.be.true;
      await ausg.unpause();
      expect(await ausg.paused()).to.be.false;
    });

    it("Should prevent minting when paused", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      await ausg.pause();

      await expect(
        ausg.connect(minter).mint(investor1.address, 1000000),
      ).to.be.revertedWithCustomError(ausg, "EnforcedPause");
    });

    it("Should prevent redemption when paused", async function () {
      const { ausg, minter, investor1 } = await loadFixture(deployFixture);
      await ausg.connect(minter).mint(investor1.address, 1000000);
      await ausg.pause();

      await expect(
        ausg.connect(investor1).redeem(500000),
      ).to.be.revertedWithCustomError(ausg, "EnforcedPause");
    });
  });
});

async function getBlockTimestamp(): Promise<number> {
  const block = await ethers.provider.getBlock("latest");
  return block!.timestamp;
}
