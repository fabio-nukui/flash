const CurveSwap = artifacts.require("CurveSwap");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(
        CurveSwap,
        {from: accounts[0]}
    )
}
