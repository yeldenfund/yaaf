require("@nomicfoundation/hardhat-verify");
require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const raw = process.env.PRIVATE_KEY_NEW || "";
const ACCOUNTS = raw.length >= 64
  ? [raw.startsWith("0x") ? raw : "0x" + raw]
  : [];   // sem chave: nenhuma conta, nada e assinado. Nunca usar chave de preenchimento.

module.exports = {
  solidity: {
    version: "0.8.20",
    settings: { optimizer: { enabled: true, runs: 200 } }
  },
  networks: {
    hardhat: { chainId: 31337 },
    sepolia: {
      url: process.env.ETH_RPC_URL || "https://rpc.sepolia.org",
      accounts: ACCOUNTS,
      chainId: 11155111
    },
    polygon: {
      url: process.env.POLYGON_RPC_URL || "https://polygon-rpc.com",
      accounts: ACCOUNTS,
      chainId: 137,
      gasPrice: 50000000000
    }
  },
  etherscan: {
  apiKey: {
    polygon: process.env.POLYGONSCAN_KEY
  },
  customChains: [
    {
      network: "polygon",
      chainId: 137,
      urls: {
        apiURL: "https://api.etherscan.io/v2/api?chainid=137",
        browserURL: "https://polygonscan.com"
      }
    }
  ]
},
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts"
  }
};
