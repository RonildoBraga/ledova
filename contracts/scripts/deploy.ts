import { ethers } from "hardhat";

async function main() {
  const [deployer] = await ethers.getSigners();
  const { chainId } = await ethers.provider.getNetwork();

  if (chainId !== 31337n && chainId !== 1337n) {
    throw new Error(
      "This example deploy script is restricted to local development networks.",
    );
  }

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

  console.log("\n3. Creating sample ShareToken...");
  const tx = await factory.createShareToken(
    "Example Company Shares",
    "DEMO",
    "TEST-COMPANY",
    10000000n,
    deployer.address,
  );

  const receipt = await tx.wait();

  const event = receipt?.logs.find(
    (log: any) =>
      factory.interface.parseLog({
        topics: log.topics as string[],
        data: log.data,
      })?.name === "ShareTokenCreated",
  );

  const parsedEvent = factory.interface.parseLog({
    topics: event!.topics as string[],
    data: event!.data,
  });

  const shareTokenAddress = parsedEvent?.args.tokenAddress;
  console.log("   Ledova ShareToken deployed to:", shareTokenAddress);

  console.log("\n4. Adding test accounts to whitelist...");
  // Public Besu/Truffle development accounts. These are fixtures, not Ledova
  // users or recommended accounts, and this script refuses non-local chains.
  const testAccounts = [
    ethers.getAddress("0xfe3b557e8fb62b89f4916b721be55ceb828dbd73"),
    ethers.getAddress("0x627306090abaB3A6e1400e9345bC60c78a8BEf57"),
    ethers.getAddress("0xf17f52151EbEF6C7334FAD080c5704D77216b732"),
  ];

  const batchTx = await whitelist.batchAddToWhitelist(testAccounts);
  await batchTx.wait();
  console.log("   Added 3 test accounts to whitelist");

  console.log("\n5. Minting initial shares...");
  const shareToken = await ethers.getContractAt(
    "ShareToken",
    shareTokenAddress,
  );

  const mintTx = await shareToken.mint(testAccounts[0], 1000000n);
  await mintTx.wait();
  console.log("   Minted 1,000,000 shares to first test account");

  console.log("\n========================================");
  console.log("Deployment Summary");
  console.log("========================================");
  console.log(`WhitelistRegistry:    ${whitelistAddress}`);
  console.log(`ShareTokenFactory:    ${factoryAddress}`);
  console.log(`Ledova ShareToken: ${shareTokenAddress}`);
  console.log("\nTest Accounts Whitelisted:");
  testAccounts.forEach((address) => console.log(`  ${address}`));
  console.log("\nDeployment complete!");

  return {
    whitelist: whitelistAddress,
    factory: factoryAddress,
    shareToken: shareTokenAddress,
  };
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
