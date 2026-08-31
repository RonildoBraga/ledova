import { expect } from "chai";
import { ethers } from "hardhat";
import {
  ShareToken,
  ShareTokenFactory,
  WhitelistRegistry,
} from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("ShareTokenFactory", function () {
  let whitelist: WhitelistRegistry;
  let factory: ShareTokenFactory;
  let owner: SignerWithAddress;
  let company1: SignerWithAddress;
  let company2: SignerWithAddress;
  let investor: SignerWithAddress;

  beforeEach(async function () {
    [owner, company1, company2, investor] = await ethers.getSigners();

    const WhitelistRegistry =
      await ethers.getContractFactory("WhitelistRegistry");
    whitelist = await WhitelistRegistry.deploy(owner.address);
    await whitelist.waitForDeployment();

    const ShareTokenFactory =
      await ethers.getContractFactory("ShareTokenFactory");
    factory = await ShareTokenFactory.deploy(
      await whitelist.getAddress(),
      owner.address,
    );
    await factory.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should set the correct owner", async function () {
      expect(await factory.owner()).to.equal(owner.address);
    });

    it("Should set the correct whitelist registry", async function () {
      expect(await factory.whitelist()).to.equal(await whitelist.getAddress());
    });

    it("Should start with zero deployed tokens", async function () {
      expect(await factory.getDeployedTokenCount()).to.equal(0);
    });

    it("Should revert if whitelist is zero address", async function () {
      const ShareTokenFactory =
        await ethers.getContractFactory("ShareTokenFactory");
      await expect(
        ShareTokenFactory.deploy(ethers.ZeroAddress, owner.address),
      ).to.be.revertedWithCustomError(factory, "InvalidParameters");
    });
  });

  describe("Creating ShareTokens", function () {
    const tokenParams = {
      name: "Test Company Shares",
      symbol: "TEST",
      identifier: "12345678901",
      authorizedShares: 1000000n,
    };

    it("Should create a new ShareToken", async function () {
      const tx = await factory.createShareToken(
        tokenParams.name,
        tokenParams.symbol,
        tokenParams.identifier,
        tokenParams.authorizedShares,
        company1.address,
      );

      const receipt = await tx.wait();

      const event = receipt?.logs.find(
        (log) =>
          factory.interface.parseLog({
            topics: log.topics as string[],
            data: log.data,
          })?.name === "ShareTokenCreated",
      );

      expect(event).to.not.be.undefined;

      const parsedEvent = factory.interface.parseLog({
        topics: event!.topics as string[],
        data: event!.data,
      });

      const tokenAddress = parsedEvent?.args.tokenAddress;
      expect(tokenAddress).to.not.equal(ethers.ZeroAddress);

      expect(await factory.isDeployedToken(tokenAddress)).to.equal(true);
      expect(await factory.getDeployedTokenCount()).to.equal(1);
    });

    it("Should emit ShareTokenCreated event", async function () {
      await expect(
        factory.createShareToken(
          tokenParams.name,
          tokenParams.symbol,
          tokenParams.identifier,
          tokenParams.authorizedShares,
          company1.address,
        ),
      ).to.emit(factory, "ShareTokenCreated");
    });

    it("Should register token by identifier", async function () {
      await factory.createShareToken(
        tokenParams.name,
        tokenParams.symbol,
        tokenParams.identifier,
        tokenParams.authorizedShares,
        company1.address,
      );

      const tokenAddress = await factory.getTokenByIdentifier(
        tokenParams.identifier,
      );
      expect(tokenAddress).to.not.equal(ethers.ZeroAddress);
    });

    it("Should revert if identifier already exists", async function () {
      await factory.createShareToken(
        tokenParams.name,
        tokenParams.symbol,
        tokenParams.identifier,
        tokenParams.authorizedShares,
        company1.address,
      );

      await expect(
        factory.createShareToken(
          "Another Company",
          "ANOTHER",
          tokenParams.identifier,
          500000n,
          company2.address,
        ),
      ).to.be.revertedWithCustomError(factory, "CompanyAlreadyExists");
    });

    it("Should revert if identifier is empty", async function () {
      await expect(
        factory.createShareToken(
          tokenParams.name,
          tokenParams.symbol,
          "",
          tokenParams.authorizedShares,
          company1.address,
        ),
      ).to.be.revertedWithCustomError(factory, "InvalidParameters");
    });

    it("Should revert if company owner is zero address", async function () {
      await expect(
        factory.createShareToken(
          tokenParams.name,
          tokenParams.symbol,
          tokenParams.identifier,
          tokenParams.authorizedShares,
          ethers.ZeroAddress,
        ),
      ).to.be.revertedWithCustomError(factory, "InvalidParameters");
    });

    it("Should revert if authorized shares is zero", async function () {
      await expect(
        factory.createShareToken(
          tokenParams.name,
          tokenParams.symbol,
          tokenParams.identifier,
          0n,
          company1.address,
        ),
      ).to.be.revertedWithCustomError(factory, "InvalidParameters");
    });

    it("Should revert if caller is not owner", async function () {
      await expect(
        factory
          .connect(company1)
          .createShareToken(
            tokenParams.name,
            tokenParams.symbol,
            tokenParams.identifier,
            tokenParams.authorizedShares,
            company1.address,
          ),
      ).to.be.revertedWithCustomError(factory, "OwnableUnauthorizedAccount");
    });
  });

  describe("Multiple Tokens", function () {
    it("Should create multiple tokens", async function () {
      await factory.createShareToken(
        "Company A Shares",
        "CMPA",
        "11111111111",
        1000000n,
        company1.address,
      );

      await factory.createShareToken(
        "Company B Shares",
        "CMPB",
        "22222222222",
        2000000n,
        company2.address,
      );

      expect(await factory.getDeployedTokenCount()).to.equal(2);
    });

    it("Should track deployed tokens", async function () {
      await factory.createShareToken(
        "Company A Shares",
        "CMPA",
        "11111111111",
        1000000n,
        company1.address,
      );

      const tokenAddress = await factory.deployedTokens(0);
      expect(await factory.isDeployedToken(tokenAddress)).to.equal(true);
    });
  });

  describe("Deployed Token Functionality", function () {
    let shareToken: ShareToken;

    beforeEach(async function () {
      const tx = await factory.createShareToken(
        "Test Company Shares",
        "TEST",
        "12345678901",
        1000000n,
        company1.address,
      );

      const receipt = await tx.wait();
      const event = receipt?.logs.find(
        (log) =>
          factory.interface.parseLog({
            topics: log.topics as string[],
            data: log.data,
          })?.name === "ShareTokenCreated",
      );

      const parsedEvent = factory.interface.parseLog({
        topics: event!.topics as string[],
        data: event!.data,
      });

      const tokenAddress = parsedEvent?.args.tokenAddress;
      shareToken = await ethers.getContractAt("ShareToken", tokenAddress);

      await whitelist.addToWhitelist(investor.address);
    });

    it("Should allow company to mint shares", async function () {
      await shareToken.connect(company1).mint(investor.address, 1000n);

      expect(await shareToken.balanceOf(investor.address)).to.equal(1000n);
    });

    it("Should use shared whitelist registry", async function () {
      expect(await shareToken.whitelist()).to.equal(
        await whitelist.getAddress(),
      );

      await expect(
        shareToken.connect(company1).mint(company2.address, 1000n),
      ).to.be.revertedWithCustomError(shareToken, "RecipientNotWhitelisted");

      await whitelist.addToWhitelist(company2.address);
      await shareToken.connect(company1).mint(company2.address, 1000n);

      expect(await shareToken.balanceOf(company2.address)).to.equal(1000n);
    });
  });
});
