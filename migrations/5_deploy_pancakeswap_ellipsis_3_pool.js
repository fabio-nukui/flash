const PancakeswapEllipsis3Pool = artifacts.require("PancakeswapEllipsis3Pool");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(
        PancakeswapEllipsis3Pool,
        {from: accounts[0]}
    )
}
