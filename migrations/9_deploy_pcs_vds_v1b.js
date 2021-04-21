const PcsVdsV1B = artifacts.require("PcsVdsV1B");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsVdsV1B)
}
