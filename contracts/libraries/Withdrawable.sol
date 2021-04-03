// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import { IERC20 } from "../interfaces/common/IERC20.sol";

contract Withdrawable {
    address payable owner = payable(msg.sender);

    modifier restricted() {
        require(msg.sender == owner);
        _;
    }

    receive () external payable {}

    function withdrawToken(address _tokenAddress) public restricted {
        uint256 balance = IERC20(_tokenAddress).balanceOf(address(this));
        IERC20(_tokenAddress).transfer(owner, balance);
    }

    function withdrawEther() public restricted {
        address self = address(this);
        // workaround for a possible solidity bug
        uint256 balance = self.balance;
        owner.transfer(balance);
    }
}
