import { expect } from "chai";
import { ethers } from "hardhat";
import { AUDY } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("AUDY", function () {
  let stablecoin: AUDY;
  let owner: SignerWithAddress;
  let minter: SignerWithAddress;
  let user1: SignerWithAddress;
  let user2: SignerWithAddress;

  beforeEach(async function () {
    [owner, minter, user1, user2] = await ethers.getSigners();

    const AUDY = await ethers.getContractFactory("AUDY");
    stablecoin = await AUDY.deploy(owner.address);
    await stablecoin.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should set the correct name and symbol", async function () {
      expect(await stablecoin.name()).to.equal("AUDY");
      expect(await stablecoin.symbol()).to.equal("AUDY");
    });

    it("Should set the correct owner", async function () {
      expect(await stablecoin.owner()).to.equal(owner.address);
    });

    it("Should have 2 decimals (cents precision)", async function () {
      expect(await stablecoin.decimals()).to.equal(2);
    });

    it("Should start with zero total supply", async function () {
      expect(await stablecoin.totalSupply()).to.equal(0);
    });

    it("Should not be paused initially", async function () {
      expect(await stablecoin.paused()).to.equal(false);
    });
  });

  describe("Minter Management", function () {
    it("Should add minter", async function () {
      await expect(stablecoin.addMinter(minter.address))
        .to.emit(stablecoin, "MinterAdded")
        .withArgs(minter.address);

      expect(await stablecoin.minters(minter.address)).to.equal(true);
    });

    it("Should remove minter", async function () {
      await stablecoin.addMinter(minter.address);

      await expect(stablecoin.removeMinter(minter.address))
        .to.emit(stablecoin, "MinterRemoved")
        .withArgs(minter.address);

      expect(await stablecoin.minters(minter.address)).to.equal(false);
    });

    it("Should revert if non-owner tries to add minter", async function () {
      await expect(
        stablecoin.connect(user1).addMinter(minter.address),
      ).to.be.revertedWithCustomError(stablecoin, "OwnableUnauthorizedAccount");
    });

    it("Should revert if non-owner tries to remove minter", async function () {
      await stablecoin.addMinter(minter.address);

      await expect(
        stablecoin.connect(user1).removeMinter(minter.address),
      ).to.be.revertedWithCustomError(stablecoin, "OwnableUnauthorizedAccount");
    });
  });

  describe("Minting", function () {
    beforeEach(async function () {
      await stablecoin.addMinter(minter.address);
    });

    it("Should allow minter to mint tokens", async function () {
      const amount = 100000n;

      await stablecoin.connect(minter).mint(user1.address, amount);

      expect(await stablecoin.balanceOf(user1.address)).to.equal(amount);
      expect(await stablecoin.totalSupply()).to.equal(amount);
    });

    it("Should revert if non-minter tries to mint", async function () {
      await expect(
        stablecoin.connect(user1).mint(user1.address, 1000n),
      ).to.be.revertedWithCustomError(stablecoin, "NotMinter");
    });

    it("Should revert minting when paused", async function () {
      await stablecoin.pause();

      await expect(
        stablecoin.connect(minter).mint(user1.address, 1000n),
      ).to.be.revertedWithCustomError(stablecoin, "EnforcedPause");
    });
  });

  describe("Burning", function () {
    beforeEach(async function () {
      await stablecoin.addMinter(minter.address);
      await stablecoin.connect(minter).mint(user1.address, 10000n);
    });

    it("Should allow user to burn their tokens", async function () {
      await stablecoin.connect(user1).burn(5000n);

      expect(await stablecoin.balanceOf(user1.address)).to.equal(5000n);
      expect(await stablecoin.totalSupply()).to.equal(5000n);
    });

    it("Should revert if burning more than balance", async function () {
      await expect(
        stablecoin.connect(user1).burn(20000n),
      ).to.be.revertedWithCustomError(stablecoin, "ERC20InsufficientBalance");
    });
  });

  describe("Transfers", function () {
    beforeEach(async function () {
      await stablecoin.addMinter(minter.address);
      await stablecoin.connect(minter).mint(user1.address, 10000n);
    });

    it("Should allow transfers", async function () {
      await stablecoin.connect(user1).transfer(user2.address, 5000n);

      expect(await stablecoin.balanceOf(user1.address)).to.equal(5000n);
      expect(await stablecoin.balanceOf(user2.address)).to.equal(5000n);
    });

    it("Should allow transferFrom with approval", async function () {
      await stablecoin.connect(user1).approve(user2.address, 5000n);
      await stablecoin
        .connect(user2)
        .transferFrom(user1.address, user2.address, 5000n);

      expect(await stablecoin.balanceOf(user2.address)).to.equal(5000n);
    });
  });

  describe("Pause/Unpause", function () {
    beforeEach(async function () {
      await stablecoin.addMinter(minter.address);
      await stablecoin.connect(minter).mint(user1.address, 10000n);
    });

    it("Should pause the contract", async function () {
      await stablecoin.pause();
      expect(await stablecoin.paused()).to.equal(true);
    });

    it("Should unpause the contract", async function () {
      await stablecoin.pause();
      await stablecoin.unpause();
      expect(await stablecoin.paused()).to.equal(false);
    });

    it("Should allow transfers when paused (stablecoin transfers not restricted)", async function () {
      await stablecoin.pause();

      await stablecoin.connect(user1).transfer(user2.address, 1000n);
      expect(await stablecoin.balanceOf(user2.address)).to.equal(1000n);
    });

    it("Should revert if non-owner tries to pause", async function () {
      await expect(
        stablecoin.connect(user1).pause(),
      ).to.be.revertedWithCustomError(stablecoin, "OwnableUnauthorizedAccount");
    });
  });
});
