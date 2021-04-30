const PcsPcs2V2B = artifacts.require("PcsPcs2V2B");

module.exports = function(deployer, network, accounts) {
    deployer.deploy(PcsPcs2V2B)
}
