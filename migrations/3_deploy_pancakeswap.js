const PancakeSwap = artifacts.require("PancakeSwap");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(
        PancakeSwap,
        {from: accounts[0]}
    )
}
