import { ethers } from "hardhat";

const FACTORY_ADDRESS = process.env.FACTORY_ADDRESS || "";
const WHITELIST_ADDRESS = process.env.WHITELIST_ADDRESS || "";
const TOKEN_NAME = process.env.TOKEN_NAME || "Example Share Token";
const TOKEN_SYMBOL = process.env.TOKEN_SYMBOL || "DEMO";
const COMPANY_IDENTIFIER = process.env.COMPANY_IDENTIFIER || "TEST-COMPANY";
const AUTHORIZED_SHARES = BigInt(process.env.AUTHORIZED_SHARES || "1000000");
const INITIAL_MINT = BigInt(process.env.INITIAL_MINT || "1000000");

function requireAddress(name: string, value: string): string {
  if (!ethers.isAddress(value) || value === ethers.ZeroAddress) {
    throw new Error(`${name} must be a configured non-zero address.`);
  }
  return value;
}

async function main() {
  const [deployer] = await ethers.getSigners();
  const { chainId } = await ethers.provider.getNetwork();

  if (![1337n, 31337n, 84532n].includes(chainId)) {
    throw new Error(
      "This example deploy script supports local networks and Base Sepolia only.",
    );
  }
  if (INITIAL_MINT < 0n || INITIAL_MINT > AUTHORIZED_SHARES) {
    throw new Error("INITIAL_MINT must be between zero and AUTHORIZED_SHARES.");
  }

  const factoryAddress = requireAddress("FACTORY_ADDRESS", FACTORY_ADDRESS);
  const whitelistAddress = requireAddress(
    "WHITELIST_ADDRESS",
    WHITELIST_ADDRESS,
  );
  const factory = await ethers.getContractAt(
    "ShareTokenFactory",
    factoryAddress,
  );
  const whitelist = await ethers.getContractAt(
    "WhitelistRegistry",
    whitelistAddress,
  );

  const existing = await factory.getTokenByIdentifier(COMPANY_IDENTIFIER);
  if (existing !== ethers.ZeroAddress) {
    console.log("A token already exists for the configured identifier.");
    return;
  }

  if (!(await whitelist.isWhitelisted(deployer.address))) {
    const whitelistTransaction = await whitelist.addToWhitelist(
      deployer.address,
    );
    await whitelistTransaction.wait();
  }

  const transaction = await factory.createShareToken(
    TOKEN_NAME,
    TOKEN_SYMBOL,
    COMPANY_IDENTIFIER,
    AUTHORIZED_SHARES,
    deployer.address,
  );
  const receipt = await transaction.wait();
  const event = receipt?.logs.find((log) => {
    try {
      return factory.interface.parseLog(log)?.name === "ShareTokenCreated";
    } catch {
      return false;
    }
  });
  if (!event) {
    throw new Error("ShareTokenCreated event was not emitted.");
  }

  const parsedEvent = factory.interface.parseLog(event);
  const tokenAddress = parsedEvent?.args.tokenAddress;
  if (INITIAL_MINT > 0n) {
    const token = await ethers.getContractAt("ShareToken", tokenAddress);
    const mintTransaction = await token.mint(deployer.address, INITIAL_MINT);
    await mintTransaction.wait();
  }

  console.log(
    "Example share token deployed on an approved development network.",
  );
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "Unknown error";
  console.error(message);
  process.exitCode = 1;
});
