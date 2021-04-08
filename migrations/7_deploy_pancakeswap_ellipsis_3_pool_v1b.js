const PancakeswapEllipsis3PoolV1B = artifacts.require("PancakeswapEllipsis3PoolV1B");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PancakeswapEllipsis3PoolV1B)
}
