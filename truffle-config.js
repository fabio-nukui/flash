require('dotenv').config()

const HDWalletProvider = require('@truffle/hdwallet-provider')

const privateKey = process.env.PRIVATE_KEY

module.exports = {
  networks: {
    dev: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "http://localhost:8547"
      }),
      port: 8547,
      network_id: '*',
      gas: 9000000,
      gasPrice: 5000000000,
      skipDryRun: true,
    },
    testnet: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "https://data-seed-prebsc-1-s1.binance.org:8545"
      }),
      network_id: 97,
      confirmations: 1,
      timeoutBlocks: 200,
      gas: 9000000,
      gasPrice: 5000000001,
      skipDryRun: true
    },
    bsc: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "https://bsc-dataseed1.binance.org"
      }),
      network_id: 56,
      confirmations: 3,
      timeoutBlocks: 200,
      gas: 9000000,
      gasPrice: 5000000001
    },
  },

  // Set default mocha options here, use special reporters etc.
  mocha: {
    // timeout: 100000
  },

  // Configure your compilers
  compilers: {
    solc: {
      version: "0.6.12",
      settings: {          // See the solidity docs for advice about optimization and evmVersion
       optimizer: {
         enabled: true,
         runs: 10000
       },
      }
    }
  }
}
