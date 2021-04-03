// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import "../interfaces/common/IERC20.sol";
import "../interfaces/curve/ICurveFiPool.sol";

contract CurveSwap {
    // Addresses
    address payable immutable owner = payable(msg.sender);

    address constant ellipsis3pool = 0x160CAed03795365F3A589f10C379FfA7d75d4E76;

    address constant BUSD = 0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56;
    address constant USDC = 0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d;
    address constant USDT = 0x55d398326f99059fF775485246999027B3197955;

    // Currency mappings
    mapping(int128 => address) public currencies;

    constructor() public {
        currencies[0] = BUSD;
        currencies[1] = USDC;
        currencies[2] = USDT;
    }

    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "caller is not the owner!");
        _;
    }

    // Allow the contract to receive Ether
    receive() external payable {}

    function exchange(
        int128 from,
        int128 to,
        uint256 amount,
        uint256 minOut
    ) external {
        IERC20(currencies[from]).approve(ellipsis3pool, amount);
        ICurveFiPool curve = ICurveFiPool(ellipsis3pool);
        curve.exchange(from, to, amount, minOut);
    }

    // KEEP THIS FUNCTION IN CASE THE CONTRACT RECEIVES TOKENS!
    function withdrawToken(address _tokenAddress) public onlyOwner {
        uint256 balance = IERC20(_tokenAddress).balanceOf(address(this));
        IERC20(_tokenAddress).transfer(owner, balance);
    }

    // KEEP THIS FUNCTION IN CASE THE CONTRACT KEEPS LEFTOVER ETHER!
    function withdrawEther() public onlyOwner {
        address self = address(this);
        // workaround for a possible solidity bug
        uint256 balance = self.balance;
        owner.transfer(balance);
    }
}
