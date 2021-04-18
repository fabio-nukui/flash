/**
 * @type import('hardhat/config').HardhatUserConfig
 */
module.exports = {
  solidity: '0.6.12',
  networks: {
    hardhat: {
      chainId: 56,
      gas: 'auto',
      gasPrice: 5000000001,
      blockGasLimit: 40000000
    },
    forking: {
      url: 'http://localhost:8546',
      chainId: 57,
    }
  }
};
