const PcsPcs2V1 = artifacts.require("PcsPcs2V1");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsPcs2V1)
}
