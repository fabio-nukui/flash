// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import "../interfaces/common/IERC20.sol";

contract Withdrawable {
    address payable owner = payable(msg.sender);

    modifier restricted() {
        require(msg.sender == owner, 'Withdrawable: RESTRICTED');
        _;
    }

    receive() external payable {}

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
