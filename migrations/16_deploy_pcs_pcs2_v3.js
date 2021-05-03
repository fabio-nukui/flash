const PcsPcs2V3 = artifacts.require("PcsPcs2V3");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsPcs2V3)
}
