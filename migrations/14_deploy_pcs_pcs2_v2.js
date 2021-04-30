const PcsPcs2V2 = artifacts.require("PcsPcs2V2");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsPcs2V2)
}
