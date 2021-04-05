const PancakeswapEllipsis3PoolV2 = artifacts.require("PancakeswapEllipsis3PoolV2");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PancakeswapEllipsis3PoolV2)
}
