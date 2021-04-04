const UnprofitableFlashSwap = artifacts.require("UnprofitableFlashSwap");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(
        UnprofitableFlashSwap,
        {from: accounts[0]}
    )
}
