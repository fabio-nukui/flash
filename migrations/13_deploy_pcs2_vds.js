const Pcs2VdsV1 = artifacts.require("Pcs2VdsV1");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(Pcs2VdsV1)
}
