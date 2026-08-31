import { ethers } from "hardhat";
import { assertTestDeploymentNetwork } from "./network-safety";

async function main() {
  await assertTestDeploymentNetwork();
  const [deployer] = await ethers.getSigners();

  console.log("Deploying AUDY with account:", deployer.address);
  console.log(
    "Account balance:",
    (await ethers.provider.getBalance(deployer.address)).toString(),
  );

  console.log("\n1. Deploying AUDY...");
  const AUDY = await ethers.getContractFactory("AUDY");
  const stablecoin = await AUDY.deploy(deployer.address);
  await stablecoin.waitForDeployment();
  const stablecoinAddress = await stablecoin.getAddress();
  console.log("   AUDY deployed to:", stablecoinAddress);

  console.log("\n2. Adding deployer as minter...");
  const addMinterTx = await stablecoin.addMinter(deployer.address);
  await addMinterTx.wait();
  console.log("   Deployer added as minter");

  console.log("\n3. Minting test tokens to deployer...");
  const mintAmount = 1000000n * 100n;
  const mintTx = await stablecoin.mint(deployer.address, mintAmount);
  await mintTx.wait();
  console.log("   Minted 1,000,000.00 AUDY to deployer");

  console.log("\n========================================");
  console.log("AUDY Deployment Summary");
  console.log("========================================");
  console.log(`AUDY Address: ${stablecoinAddress}`);
  console.log(`Symbol: AUDY`);
  console.log(`Decimals: 2`);
  console.log(`Owner: ${deployer.address}`);
  console.log(`Initial Minter: ${deployer.address}`);
  console.log("\nDeployment complete!");

  return {
    stablecoin: stablecoinAddress,
  };
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
