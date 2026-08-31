import { ethers } from "hardhat";
import * as fs from "fs";
import { assertTestDeploymentNetwork } from "./network-safety";

async function main() {
  await assertTestDeploymentNetwork();
  const [deployer] = await ethers.getSigners();

  console.log("Deploying contracts with the account:", deployer.address);
  console.log(
    "Account balance:",
    (await ethers.provider.getBalance(deployer.address)).toString(),
  );

  console.log("\n1. Deploying WhitelistRegistry...");
  const WhitelistRegistry =
    await ethers.getContractFactory("WhitelistRegistry");
  const whitelist = await WhitelistRegistry.deploy(deployer.address);
  await whitelist.waitForDeployment();
  const whitelistAddress = await whitelist.getAddress();
  console.log("   WhitelistRegistry deployed to:", whitelistAddress);

  console.log("\n2. Deploying ShareTokenFactory...");
  const ShareTokenFactory =
    await ethers.getContractFactory("ShareTokenFactory");
  const factory = await ShareTokenFactory.deploy(
    whitelistAddress,
    deployer.address,
  );
  await factory.waitForDeployment();
  const factoryAddress = await factory.getAddress();
  console.log("   ShareTokenFactory deployed to:", factoryAddress);

  console.log("\n3. Deploying AUDY...");
  const AUDY = await ethers.getContractFactory("AUDY");
  const stablecoin = await AUDY.deploy(deployer.address);
  await stablecoin.waitForDeployment();
  const stablecoinAddress = await stablecoin.getAddress();
  console.log("   AUDY deployed to:", stablecoinAddress);

  console.log("\n4. Setting up AUDY...");
  const addMinterTx = await stablecoin.addMinter(deployer.address);
  await addMinterTx.wait();
  console.log("   Deployer added as minter");

  console.log("\n5. Deploying AtomicSwap...");
  const AtomicSwap = await ethers.getContractFactory("AtomicSwap");
  const atomicSwap = await AtomicSwap.deploy(
    whitelistAddress,
    deployer.address,
  );
  await atomicSwap.waitForDeployment();
  const atomicSwapAddress = await atomicSwap.getAddress();
  console.log("   AtomicSwap deployed to:", atomicSwapAddress);

  const chainId = await atomicSwap.getChainId();

  console.log("\n6. Configuring AtomicSwap...");
  const approveStableTx = await atomicSwap.setPaymentTokenApproval(
    stablecoinAddress,
    true,
  );
  await approveStableTx.wait();
  console.log("   Approved stablecoin as payment token");

  console.log("\n========================================");
  console.log("Deployment Summary");
  console.log("========================================");
  console.log(`WhitelistRegistry:    ${whitelistAddress}`);
  console.log(`ShareTokenFactory:    ${factoryAddress}`);
  console.log(`AUDY:                 ${stablecoinAddress}`);
  console.log(`AtomicSwap:           ${atomicSwapAddress}`);
  console.log("\nEIP-712 Domain (AtomicSwap):");
  console.log("  Name: LedovaAtomicSwap");
  console.log("  Version: 1");
  console.log(`  Chain ID: ${chainId.toString()}`);
  console.log(`  Verifying Contract: ${atomicSwapAddress}`);

  const envContent = `# Contract addresses deployed by deploy-all.ts
# Generated at: ${new Date().toISOString()}
WHITELIST_CONTRACT_ADDRESS=${whitelistAddress}
SHARE_TOKEN_FACTORY_ADDRESS=${factoryAddress}
ATOMIC_SWAP_ADDRESS=${atomicSwapAddress}
STABLECOIN_CONTRACT_ADDRESS=${stablecoinAddress}
`;

  const envPath = "../.deployed-contracts.env";
  fs.writeFileSync(envPath, envContent);
  console.log(`\nContract addresses written to: ${envPath}`);
  console.log("\nDeployment complete!");

  return {
    whitelist: whitelistAddress,
    factory: factoryAddress,
    stablecoin: stablecoinAddress,
    atomicSwap: atomicSwapAddress,
  };
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
