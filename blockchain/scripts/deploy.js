import { ethers } from "hardhat";
import { writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const NETWORK_ID = "tradeshield-local:31337";

/**
 * Deploy TradeShieldAudit to the local Hardhat node.
 *
 * The first Hardhat account is the authorized backend signer.  After deployment
 * this script writes blockchain/deployment.json so the Flask backend can read
 * the contract address automatically without needing BLOCKCHAIN_CONTRACT_ADDRESS
 * set in .env.
 *
 * To wire the backend:
 *   BLOCKCHAIN_NODE_URL=http://127.0.0.1:8545
 *   BLOCKCHAIN_PRIVATE_KEY=<first Hardhat account private key>
 *   # contract address is read from deployment.json automatically
 */
async function main() {
  const [backend, admin] = await ethers.getSigners();

  console.log("Deploying TradeShieldAudit to local Hardhat node...");
  console.log("backend address :", backend.address);
  console.log("admin address   :", admin.address);
  console.log("networkId       :", NETWORK_ID);

  const TradeShieldAudit = await ethers.getContractFactory("TradeShieldAudit");
  const contract = await TradeShieldAudit.deploy(NETWORK_ID, backend.address, admin.address);
  await contract.waitForDeployment();

  const addr = await contract.getAddress();
  const network = await contract.runner.provider.getNetwork();
  console.log("TradeShieldAudit deployed to:", addr);
  console.log("network chainId             :", network.chainId.toString());

  // Write deployment.json one level up (blockchain/deployment.json) so the
  // Python backend can auto-discover the contract address.
  const deploymentPath = join(__dirname, "..", "deployment.json");
  const deployment = {
    address: addr,
    backend: backend.address,
    admin: admin.address,
    networkId: NETWORK_ID,
    chainId: network.chainId.toString(),
    deployedAt: new Date().toISOString(),
  };
  writeFileSync(deploymentPath, JSON.stringify(deployment, null, 2));
  console.log("Deployment info written to:", deploymentPath);

  return deployment;
}

main().then(() => { process.exitCode = 0; }).catch((err) => {
  console.error(err);
  process.exit(1);
});
