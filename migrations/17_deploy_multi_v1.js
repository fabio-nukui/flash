const MultiV1 = artifacts.require("MultiV1");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(MultiV1)
}
