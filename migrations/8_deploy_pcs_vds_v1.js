const PcsVdsV1 = artifacts.require("PcsVdsV1");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsVdsV1)
}
