import { ethers } from "hardhat";

const ALLOWED_DEPLOYMENT_CHAIN_IDS = new Set([1337n, 31337n, 84532n]);

export async function assertTestDeploymentNetwork(): Promise<void> {
  const { chainId } = await ethers.provider.getNetwork();
  if (!ALLOWED_DEPLOYMENT_CHAIN_IDS.has(chainId)) {
    throw new Error(
      "Deployment scripts are restricted to local development networks and Base Sepolia.",
    );
  }
}
