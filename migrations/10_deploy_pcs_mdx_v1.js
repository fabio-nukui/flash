const PcsMdxV1 = artifacts.require("PcsMdxV1");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsMdxV1)
}
