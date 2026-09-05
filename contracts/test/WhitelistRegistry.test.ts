import { expect } from "chai";
import { ethers } from "hardhat";
import { WhitelistRegistry } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("WhitelistRegistry", function () {
  let whitelist: WhitelistRegistry;
  let owner: SignerWithAddress;
  let investor1: SignerWithAddress;
  let investor2: SignerWithAddress;
  let investor3: SignerWithAddress;
  let nonOwner: SignerWithAddress;

  beforeEach(async function () {
    [owner, investor1, investor2, investor3, nonOwner] =
      await ethers.getSigners();

    const WhitelistRegistry =
      await ethers.getContractFactory("WhitelistRegistry");
    whitelist = await WhitelistRegistry.deploy(owner.address);
    await whitelist.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should set the correct owner", async function () {
      expect(await whitelist.owner()).to.equal(owner.address);
    });

    it("Should start with zero whitelisted addresses", async function () {
      expect(await whitelist.whitelistCount()).to.equal(0);
    });

    it("Should not be paused initially", async function () {
      expect(await whitelist.paused()).to.equal(false);
    });
  });

  describe("Adding to Whitelist", function () {
    it("Should add an address to whitelist", async function () {
      const tx = await whitelist.addToWhitelist(investor1.address);

      await expect(tx).to.emit(whitelist, "AddedToWhitelist");

      expect(await whitelist.isWhitelisted(investor1.address)).to.equal(true);
      expect(await whitelist.whitelistCount()).to.equal(1);
    });

    it("Should record KYC timestamp", async function () {
      await whitelist.addToWhitelist(investor1.address);

      const kycTime = await whitelist.kycTimestamp(investor1.address);
      expect(kycTime).to.be.greaterThan(0);
    });

    it("Should revert if address is already whitelisted", async function () {
      await whitelist.addToWhitelist(investor1.address);

      await expect(
        whitelist.addToWhitelist(investor1.address),
      ).to.be.revertedWithCustomError(whitelist, "AlreadyWhitelisted");
    });

    it("Should revert if address is zero", async function () {
      await expect(
        whitelist.addToWhitelist(ethers.ZeroAddress),
      ).to.be.revertedWithCustomError(whitelist, "InvalidAddress");
    });

    it("Should revert if caller is not owner", async function () {
      await expect(
        whitelist.connect(nonOwner).addToWhitelist(investor1.address),
      ).to.be.revertedWithCustomError(whitelist, "OwnableUnauthorizedAccount");
    });
  });

  describe("Batch Adding to Whitelist", function () {
    it("Should add multiple addresses in batch", async function () {
      const investors = [
        investor1.address,
        investor2.address,
        investor3.address,
      ];

      await whitelist.batchAddToWhitelist(investors);

      expect(await whitelist.isWhitelisted(investor1.address)).to.equal(true);
      expect(await whitelist.isWhitelisted(investor2.address)).to.equal(true);
      expect(await whitelist.isWhitelisted(investor3.address)).to.equal(true);
      expect(await whitelist.whitelistCount()).to.equal(3);
    });

    it("Should skip zero address entries in batch", async function () {
      const investors = [
        investor1.address,
        ethers.ZeroAddress,
        investor2.address,
      ];

      await whitelist.batchAddToWhitelist(investors);

      expect(await whitelist.isWhitelisted(investor1.address)).to.equal(true);
      expect(await whitelist.isWhitelisted(investor2.address)).to.equal(true);
      expect(await whitelist.whitelistCount()).to.equal(2);
    });

    it("Should skip already whitelisted addresses in batch", async function () {
      await whitelist.addToWhitelist(investor1.address);

      const investors = [investor1.address, investor2.address];

      await whitelist.batchAddToWhitelist(investors);

      expect(await whitelist.isWhitelisted(investor1.address)).to.equal(true);
      expect(await whitelist.isWhitelisted(investor2.address)).to.equal(true);
      expect(await whitelist.whitelistCount()).to.equal(2);
    });
  });

  describe("Removing from Whitelist", function () {
    beforeEach(async function () {
      await whitelist.addToWhitelist(investor1.address);
    });

    it("Should remove an address from whitelist", async function () {
      const tx = await whitelist.removeFromWhitelist(investor1.address);

      await expect(tx).to.emit(whitelist, "RemovedFromWhitelist");

      expect(await whitelist.isWhitelisted(investor1.address)).to.equal(false);
      expect(await whitelist.whitelistCount()).to.equal(0);
    });

    it("Should reset KYC timestamp when removed", async function () {
      await whitelist.removeFromWhitelist(investor1.address);

      expect(await whitelist.kycTimestamp(investor1.address)).to.equal(0);
    });

    it("Should revert if address is not whitelisted", async function () {
      await expect(
        whitelist.removeFromWhitelist(investor2.address),
      ).to.be.revertedWithCustomError(whitelist, "NotWhitelisted");
    });
  });

  describe("Pause/Unpause", function () {
    it("Should pause the contract", async function () {
      await whitelist.pause();
      expect(await whitelist.paused()).to.equal(true);
    });

    it("Should unpause the contract", async function () {
      await whitelist.pause();
      await whitelist.unpause();
      expect(await whitelist.paused()).to.equal(false);
    });

    it("Should prevent adding to whitelist when paused", async function () {
      await whitelist.pause();

      await expect(
        whitelist.addToWhitelist(investor1.address),
      ).to.be.revertedWithCustomError(whitelist, "EnforcedPause");
    });

    it("Should prevent removing from whitelist when paused", async function () {
      await whitelist.addToWhitelist(investor1.address);
      await whitelist.pause();

      await expect(
        whitelist.removeFromWhitelist(investor1.address),
      ).to.be.revertedWithCustomError(whitelist, "EnforcedPause");
    });

    it("Should prevent batch adding when paused", async function () {
      await whitelist.pause();

      await expect(
        whitelist.batchAddToWhitelist([investor1.address]),
      ).to.be.revertedWithCustomError(whitelist, "EnforcedPause");
    });
  });

  describe("View Functions", function () {
    beforeEach(async function () {
      await whitelist.addToWhitelist(investor1.address);
    });

    it("Should return correct investor info", async function () {
      const [whitelisted, kycTimestamp] = await whitelist.getInvestorInfo(
        investor1.address,
      );

      expect(whitelisted).to.equal(true);
      expect(kycTimestamp).to.be.greaterThan(0);
    });

    it("Should return false for non-whitelisted address info", async function () {
      const [whitelisted, kycTimestamp] = await whitelist.getInvestorInfo(
        investor2.address,
      );

      expect(whitelisted).to.equal(false);
      expect(kycTimestamp).to.equal(0);
    });

    it("Should return canReceive correctly", async function () {
      expect(await whitelist.canReceive(investor1.address)).to.equal(true);
      expect(await whitelist.canReceive(investor2.address)).to.equal(false);
    });

    it("Should return isWhitelisted correctly", async function () {
      expect(await whitelist.isWhitelisted(investor1.address)).to.equal(true);
      expect(await whitelist.isWhitelisted(investor2.address)).to.equal(false);
    });
  });
});
