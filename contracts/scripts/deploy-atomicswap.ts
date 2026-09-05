import { ethers } from "hardhat";
import { assertTestDeploymentNetwork } from "./network-safety";

async function main() {
  await assertTestDeploymentNetwork();
  const whitelistAddress = process.env.WHITELIST_ADDRESS;
  const stablecoinAddress = process.env.STABLECOIN_ADDRESS;
  const shareTokenAddress = process.env.SHARE_TOKEN_ADDRESS;
  const relayerAddress = process.env.RELAYER_ADDRESS;

  if (!whitelistAddress) {
    throw new Error("WHITELIST_ADDRESS environment variable not set");
  }

  const [deployer] = await ethers.getSigners();

  console.log("Deploying AtomicSwap with account:", deployer.address);
  console.log(
    "Account balance:",
    (await ethers.provider.getBalance(deployer.address)).toString(),
  );

  console.log("\n1. Deploying AtomicSwap...");
  const AtomicSwap = await ethers.getContractFactory("AtomicSwap");
  const atomicSwap = await AtomicSwap.deploy(
    whitelistAddress,
    deployer.address,
  );
  await atomicSwap.waitForDeployment();
  const atomicSwapAddress = await atomicSwap.getAddress();
  console.log("   AtomicSwap deployed to:", atomicSwapAddress);

  const domainSeparator = await atomicSwap.getDomainSeparator();
  const chainId = await atomicSwap.getChainId();
  console.log("   Domain separator:", domainSeparator);
  console.log("   Chain ID:", chainId.toString());

  if (stablecoinAddress) {
    console.log("\n2. Approving stablecoin as payment token...");
    const approveTx = await atomicSwap.setPaymentTokenApproval(
      stablecoinAddress,
      true,
    );
    await approveTx.wait();
    console.log("   Approved:", stablecoinAddress);
  }

  if (shareTokenAddress) {
    console.log("\n3. Approving share token...");
    const approveTx = await atomicSwap.setShareTokenApproval(
      shareTokenAddress,
      true,
    );
    await approveTx.wait();
    console.log("   Approved:", shareTokenAddress);
  }

  if (relayerAddress && relayerAddress !== deployer.address) {
    console.log("\n4. Adding relayer...");
    const relayerTx = await atomicSwap.setRelayer(relayerAddress, true);
    await relayerTx.wait();
    console.log("   Relayer added:", relayerAddress);
  }

  console.log("\n========================================");
  console.log("AtomicSwap Deployment Summary");
  console.log("========================================");
  console.log(`AtomicSwap Address: ${atomicSwapAddress}`);
  console.log(`Whitelist Address: ${whitelistAddress}`);
  console.log(`Owner: ${deployer.address}`);
  console.log(`Domain Separator: ${domainSeparator}`);
  console.log(`Chain ID: ${chainId.toString()}`);
  if (stablecoinAddress) {
    console.log(`Approved Payment Token: ${stablecoinAddress}`);
  }
  if (shareTokenAddress) {
    console.log(`Approved Share Token: ${shareTokenAddress}`);
  }
  if (relayerAddress) {
    console.log(`Relayer: ${relayerAddress}`);
  }
  console.log("\nEIP-712 Domain:");
  console.log("  Name: LedovaAtomicSwap");
  console.log("  Version: 1");
  console.log(`  Chain ID: ${chainId.toString()}`);
  console.log(`  Verifying Contract: ${atomicSwapAddress}`);
  console.log("\nDeployment complete!");

  return {
    atomicSwap: atomicSwapAddress,
    domainSeparator,
    chainId: chainId.toString(),
  };
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
