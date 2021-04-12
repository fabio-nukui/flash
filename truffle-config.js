require('dotenv').config()

const HDWalletProvider = require('@truffle/hdwallet-provider')

const privateKey = process.env.PRIVATE_KEY

module.exports = {
  networks: {
    development: {
      host: "127.0.0.1",     // Localhost (default: none)
      port: 7475,            // Standard BSC port (default: none)
      network_id: "*",       // Any network (default: none)
      gas: 1000000,
      gasPrice: 10000000000,
      skipDryRun: false,
    },
    testnet: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "https://data-seed-prebsc-1-s1.binance.org:8545"
      }),
      network_id: 97,
      confirmations: 1,
      timeoutBlocks: 200,
      gas: 1000000,
      gasPrice: 5001000000,
      skipDryRun: true
    },
    bsc: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "https://bsc-dataseed1.binance.org"
      }),
      network_id: 56,
      confirmations: 2,
      timeoutBlocks: 200,
      gas: 10000000,
      gasPrice: 5001000000
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
         runs: 200
       },
      }
    }
  }
}
