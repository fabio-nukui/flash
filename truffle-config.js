require('dotenv').config()

const HDWalletProvider = require('@truffle/hdwallet-provider')

const privateKey = process.env.PRIVATE_KEY

module.exports = {
  networks: {
    development: {
      host: "127.0.0.1",     // Localhost (default: none)
      port: 8545,            // Standard BSC port (default: none)
      network_id: "*",       // Any network (default: none)
    },
    testnet: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "https://data-seed-prebsc-1-s1.binance.org:8545"
      }),
      network_id: 97,
      confirmations: 3,
      timeoutBlocks: 200,
      gas: 1000000,
      gasPrice: 10000000000,
      skipDryRun: true
    },
    bsc: {
      provider: () => new HDWalletProvider({
        privateKeys: [privateKey],
        providerOrUrl: "https://bsc-dataseed1.binance.org"
      }),
      network_id: 56,
      confirmations: 5,
      timeoutBlocks: 200,
      gas: 1000000,
      gasPrice: 10000000000,
      skipDryRun: true
    },
  },

  // Set default mocha options here, use special reporters etc.
  mocha: {
    // timeout: 100000
  },

  // Configure your compilers
  compilers: {
    solc: {
      version: "0.8.3"
      // settings: {          // See the solidity docs for advice about optimization and evmVersion
      //  optimizer: {
      //    enabled: false,
      //    runs: 200
      //  },
    }
  }
}