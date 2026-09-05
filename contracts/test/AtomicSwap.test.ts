import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import {
  AtomicSwap,
  ShareToken,
  AUDY,
  WhitelistRegistry,
} from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("AtomicSwap", function () {
  let atomicSwap: AtomicSwap;
  let whitelist: WhitelistRegistry;
  let shareToken: ShareToken;
  let stablecoin: AUDY;
  let owner: SignerWithAddress;
  let seller: SignerWithAddress;
  let buyer: SignerWithAddress;
  let relayer: SignerWithAddress;

  const SHARE_AMOUNT = 1000n;
  const PAYMENT_AMOUNT = 10000n;
  const NONCE = 1n;

  const DOMAIN_NAME = "LedovaAtomicSwap";
  const DOMAIN_VERSION = "1";

  const SWAP_ORDER_TYPES = {
    SwapOrder: [
      { name: "seller", type: "address" },
      { name: "buyer", type: "address" },
      { name: "shareToken", type: "address" },
      { name: "paymentToken", type: "address" },
      { name: "shareAmount", type: "uint256" },
      { name: "paymentAmount", type: "uint256" },
      { name: "nonce", type: "uint256" },
      { name: "deadline", type: "uint256" },
    ],
  };

  async function getEIP712Domain() {
    const chainId = (await ethers.provider.getNetwork()).chainId;
    return {
      name: DOMAIN_NAME,
      version: DOMAIN_VERSION,
      chainId: chainId,
      verifyingContract: await atomicSwap.getAddress(),
    };
  }

  async function signSwapOrder(
    signer: SignerWithAddress,
    order: {
      seller: string;
      buyer: string;
      shareToken: string;
      paymentToken: string;
      shareAmount: bigint;
      paymentAmount: bigint;
      nonce: bigint;
      deadline: bigint;
    },
  ) {
    const domain = await getEIP712Domain();
    return signer.signTypedData(domain, SWAP_ORDER_TYPES, order);
  }

  beforeEach(async function () {
    [owner, seller, buyer, relayer] = await ethers.getSigners();

    const WhitelistRegistry =
      await ethers.getContractFactory("WhitelistRegistry");
    whitelist = await WhitelistRegistry.deploy(owner.address);
    await whitelist.waitForDeployment();

    await whitelist.addToWhitelist(seller.address);
    await whitelist.addToWhitelist(buyer.address);

    const ShareToken = await ethers.getContractFactory("ShareToken");
    shareToken = await ShareToken.deploy(
      "Test Shares",
      "TEST",
      await whitelist.getAddress(),
      1000000n,
      owner.address,
    );
    await shareToken.waitForDeployment();

    const AUDY = await ethers.getContractFactory("AUDY");
    stablecoin = await AUDY.deploy(owner.address);
    await stablecoin.waitForDeployment();

    const AtomicSwap = await ethers.getContractFactory("AtomicSwap");
    atomicSwap = await AtomicSwap.deploy(
      await whitelist.getAddress(),
      owner.address,
    );
    await atomicSwap.waitForDeployment();

    await atomicSwap.setShareTokenApproval(await shareToken.getAddress(), true);
    await atomicSwap.setPaymentTokenApproval(
      await stablecoin.getAddress(),
      true,
    );

    await atomicSwap.setRelayer(relayer.address, true);

    await shareToken.mint(seller.address, 10000n);
    await stablecoin.addMinter(owner.address);
    await stablecoin.mint(buyer.address, 100000n);

    await shareToken
      .connect(seller)
      .approve(await atomicSwap.getAddress(), ethers.MaxUint256);
    await stablecoin
      .connect(buyer)
      .approve(await atomicSwap.getAddress(), ethers.MaxUint256);
  });

  describe("Deployment", function () {
    it("Should set the correct owner", async function () {
      expect(await atomicSwap.owner()).to.equal(owner.address);
    });

    it("Should set the correct whitelist", async function () {
      expect(await atomicSwap.whitelist()).to.equal(
        await whitelist.getAddress(),
      );
    });

    it("Should set owner as relayer", async function () {
      expect(await atomicSwap.relayers(owner.address)).to.equal(true);
    });

    it("Should return correct domain separator", async function () {
      const domainSeparator = await atomicSwap.getDomainSeparator();
      expect(domainSeparator).to.not.equal(ethers.ZeroHash);
    });

    it("Should return correct chain ID", async function () {
      const chainId = await atomicSwap.getChainId();
      expect(chainId).to.equal(31337n);
    });
  });

  describe("Token Approval", function () {
    it("Should approve share token", async function () {
      const newToken = await (
        await ethers.getContractFactory("ShareToken")
      ).deploy(
        "New",
        "NEW",
        await whitelist.getAddress(),
        1000n,
        owner.address,
      );

      await expect(
        atomicSwap.setShareTokenApproval(await newToken.getAddress(), true),
      ).to.emit(atomicSwap, "ShareTokenApproved");

      expect(
        await atomicSwap.approvedShareTokens(await newToken.getAddress()),
      ).to.equal(true);
    });

    it("Should approve payment token", async function () {
      const newStable = await (
        await ethers.getContractFactory("AUDY")
      ).deploy(owner.address);

      await expect(
        atomicSwap.setPaymentTokenApproval(await newStable.getAddress(), true),
      ).to.emit(atomicSwap, "PaymentTokenApproved");

      expect(
        await atomicSwap.approvedPaymentTokens(await newStable.getAddress()),
      ).to.equal(true);
    });

    it("Should revert if non-owner sets approval", async function () {
      await expect(
        atomicSwap
          .connect(seller)
          .setShareTokenApproval(await shareToken.getAddress(), false),
      ).to.be.revertedWithCustomError(atomicSwap, "OwnableUnauthorizedAccount");
    });
  });

  describe("Relayer Management", function () {
    it("Should add relayer", async function () {
      const [, , , , newRelayer] = await ethers.getSigners();

      await expect(atomicSwap.setRelayer(newRelayer.address, true))
        .to.emit(atomicSwap, "RelayerUpdated")
        .withArgs(newRelayer.address, true);

      expect(await atomicSwap.relayers(newRelayer.address)).to.equal(true);
    });

    it("Should remove relayer", async function () {
      await expect(atomicSwap.setRelayer(relayer.address, false))
        .to.emit(atomicSwap, "RelayerUpdated")
        .withArgs(relayer.address, false);

      expect(await atomicSwap.relayers(relayer.address)).to.equal(false);
    });

    it("Should revert if non-owner sets relayer", async function () {
      await expect(
        atomicSwap.connect(seller).setRelayer(seller.address, true),
      ).to.be.revertedWithCustomError(atomicSwap, "OwnableUnauthorizedAccount");
    });
  });

  describe("Execute Swap", function () {
    it("Should execute atomic swap with valid signatures", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      const sellerSharesBefore = await shareToken.balanceOf(seller.address);
      const buyerSharesBefore = await shareToken.balanceOf(buyer.address);
      const sellerPaymentBefore = await stablecoin.balanceOf(seller.address);
      const buyerPaymentBefore = await stablecoin.balanceOf(buyer.address);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.emit(atomicSwap, "SwapExecuted");

      expect(await shareToken.balanceOf(seller.address)).to.equal(
        sellerSharesBefore - SHARE_AMOUNT,
      );
      expect(await shareToken.balanceOf(buyer.address)).to.equal(
        buyerSharesBefore + SHARE_AMOUNT,
      );
      expect(await stablecoin.balanceOf(seller.address)).to.equal(
        sellerPaymentBefore + PAYMENT_AMOUNT,
      );
      expect(await stablecoin.balanceOf(buyer.address)).to.equal(
        buyerPaymentBefore - PAYMENT_AMOUNT,
      );
    });

    it("Should emit correct event with order hash", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      const expectedOrderHash = await atomicSwap.getOrderHash(
        seller.address,
        buyer.address,
        await shareToken.getAddress(),
        await stablecoin.getAddress(),
        SHARE_AMOUNT,
        PAYMENT_AMOUNT,
        NONCE,
        deadline,
      );

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      )
        .to.emit(atomicSwap, "SwapExecuted")
        .withArgs(
          expectedOrderHash,
          seller.address,
          buyer.address,
          await shareToken.getAddress(),
          await stablecoin.getAddress(),
          SHARE_AMOUNT,
          PAYMENT_AMOUNT,
          NONCE,
        );
    });

    it("Should mark nonces as used after swap", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      expect(await atomicSwap.isNonceUsed(seller.address, NONCE)).to.equal(
        false,
      );
      expect(await atomicSwap.isNonceUsed(buyer.address, NONCE)).to.equal(
        false,
      );

      await atomicSwap
        .connect(relayer)
        .executeSwap(
          seller.address,
          buyer.address,
          await shareToken.getAddress(),
          await stablecoin.getAddress(),
          SHARE_AMOUNT,
          PAYMENT_AMOUNT,
          NONCE,
          deadline,
          sellerSignature,
          buyerSignature,
        );

      expect(await atomicSwap.isNonceUsed(seller.address, NONCE)).to.equal(
        true,
      );
      expect(await atomicSwap.isNonceUsed(buyer.address, NONCE)).to.equal(true);
    });

    it("Should revert with expired deadline", async function () {
      const deadline = BigInt((await time.latest()) - 100);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "OrderExpired");
    });

    it("Should revert with invalid seller signature", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const wrongSellerSignature = await signSwapOrder(buyer, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            wrongSellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "InvalidSignature");
    });

    it("Should revert with invalid buyer signature", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const wrongBuyerSignature = await signSwapOrder(seller, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            wrongBuyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "InvalidSignature");
    });

    it("Should revert with already used nonce", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await atomicSwap
        .connect(relayer)
        .executeSwap(
          seller.address,
          buyer.address,
          await shareToken.getAddress(),
          await stablecoin.getAddress(),
          SHARE_AMOUNT,
          PAYMENT_AMOUNT,
          NONCE,
          deadline,
          sellerSignature,
          buyerSignature,
        );

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "NonceAlreadyUsed");
    });

    it("Should revert if called by non-relayer", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      const [, , , , nonRelayer] = await ethers.getSigners();

      await expect(
        atomicSwap
          .connect(nonRelayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "NotRelayer");
    });

    it("Should revert if seller and buyer are same address", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: seller.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            seller.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            sellerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "SameParty");
    });

    it("Should revert with zero share amount", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: 0n,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            0n,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "InvalidAmount");
    });

    it("Should revert with zero payment amount", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: 0n,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            0n,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "InvalidAmount");
    });

    it("Should revert with unapproved share token", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const unapprovedToken = await (
        await ethers.getContractFactory("ShareToken")
      ).deploy(
        "Unapproved",
        "UAP",
        await whitelist.getAddress(),
        1000000n,
        owner.address,
      );

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await unapprovedToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await unapprovedToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "TokenNotApproved");
    });

    it("Should revert with unapproved payment token", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const unapprovedStable = await (
        await ethers.getContractFactory("AUDY")
      ).deploy(owner.address);

      const order = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await unapprovedStable.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await unapprovedStable.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "PaymentTokenNotApproved");
    });
  });

  describe("Whitelist Validation", function () {
    it("Should revert if seller not whitelisted", async function () {
      const deadline = BigInt((await time.latest()) + 86400);
      const [, , , , nonWhitelisted] = await ethers.getSigners();

      const order = {
        seller: nonWhitelisted.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(nonWhitelisted, order);
      const buyerSignature = await signSwapOrder(buyer, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            nonWhitelisted.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "NotWhitelisted");
    });

    it("Should revert if buyer not whitelisted", async function () {
      const deadline = BigInt((await time.latest()) + 86400);
      const [, , , , nonWhitelisted] = await ethers.getSigners();

      const order = {
        seller: seller.address,
        buyer: nonWhitelisted.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: SHARE_AMOUNT,
        paymentAmount: PAYMENT_AMOUNT,
        nonce: NONCE,
        deadline: deadline,
      };

      const sellerSignature = await signSwapOrder(seller, order);
      const buyerSignature = await signSwapOrder(nonWhitelisted, order);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            nonWhitelisted.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            SHARE_AMOUNT,
            PAYMENT_AMOUNT,
            NONCE,
            deadline,
            sellerSignature,
            buyerSignature,
          ),
      ).to.be.revertedWithCustomError(atomicSwap, "NotWhitelisted");
    });
  });

  describe("Helper Functions", function () {
    it("Should compute correct order hash", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const orderHash = await atomicSwap.getOrderHash(
        seller.address,
        buyer.address,
        await shareToken.getAddress(),
        await stablecoin.getAddress(),
        SHARE_AMOUNT,
        PAYMENT_AMOUNT,
        NONCE,
        deadline,
      );

      expect(orderHash).to.not.equal(ethers.ZeroHash);
    });

    it("Should compute correct struct hash", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const structHash = await atomicSwap.getStructHash(
        seller.address,
        buyer.address,
        await shareToken.getAddress(),
        await stablecoin.getAddress(),
        SHARE_AMOUNT,
        PAYMENT_AMOUNT,
        NONCE,
        deadline,
      );

      expect(structHash).to.not.equal(ethers.ZeroHash);
    });

    it("Different parameters should produce different hashes", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const hash1 = await atomicSwap.getOrderHash(
        seller.address,
        buyer.address,
        await shareToken.getAddress(),
        await stablecoin.getAddress(),
        SHARE_AMOUNT,
        PAYMENT_AMOUNT,
        NONCE,
        deadline,
      );

      const hash2 = await atomicSwap.getOrderHash(
        seller.address,
        buyer.address,
        await shareToken.getAddress(),
        await stablecoin.getAddress(),
        SHARE_AMOUNT + 1n,
        PAYMENT_AMOUNT,
        NONCE,
        deadline,
      );

      expect(hash1).to.not.equal(hash2);
    });
  });

  describe("Multiple Swaps", function () {
    it("Should allow multiple swaps with different nonces", async function () {
      const deadline = BigInt((await time.latest()) + 86400);

      const order1 = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: 100n,
        paymentAmount: 1000n,
        nonce: 1n,
        deadline: deadline,
      };

      const sellerSig1 = await signSwapOrder(seller, order1);
      const buyerSig1 = await signSwapOrder(buyer, order1);

      await atomicSwap
        .connect(relayer)
        .executeSwap(
          seller.address,
          buyer.address,
          await shareToken.getAddress(),
          await stablecoin.getAddress(),
          100n,
          1000n,
          1n,
          deadline,
          sellerSig1,
          buyerSig1,
        );

      const order2 = {
        seller: seller.address,
        buyer: buyer.address,
        shareToken: await shareToken.getAddress(),
        paymentToken: await stablecoin.getAddress(),
        shareAmount: 200n,
        paymentAmount: 2000n,
        nonce: 2n,
        deadline: deadline,
      };

      const sellerSig2 = await signSwapOrder(seller, order2);
      const buyerSig2 = await signSwapOrder(buyer, order2);

      await expect(
        atomicSwap
          .connect(relayer)
          .executeSwap(
            seller.address,
            buyer.address,
            await shareToken.getAddress(),
            await stablecoin.getAddress(),
            200n,
            2000n,
            2n,
            deadline,
            sellerSig2,
            buyerSig2,
          ),
      ).to.emit(atomicSwap, "SwapExecuted");

      expect(await shareToken.balanceOf(buyer.address)).to.equal(300n);
      expect(await stablecoin.balanceOf(seller.address)).to.equal(3000n);
    });
  });
});
