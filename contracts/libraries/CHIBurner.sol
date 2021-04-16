// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

interface ChiToken {
    function freeFromUpTo(address from, uint256 value) external;
    function freeUpTo(uint256 value) external;
}

 // TODO: Make version without chiFlag argument (8586 gas savings)
contract CHIBurner {
    ChiToken constant private chi = ChiToken(0x0000000000004946c0e9F43F4Dee607b0eF1fA1c);

    modifier discountCHIFrom(uint8 chiFlag) {
        uint256 gasStart = gasleft();

        _;

        if ((chiFlag & 0x1) == 1) {
            uint256 gasSpent = 21000 + 16 * msg.data.length + gasStart - gasleft();
            uint256 freeUpValue = (gasSpent + 14154) / 41947;

            chi.freeFromUpTo(msg.sender, freeUpValue);
        }
    }

    modifier discountCHI(uint8 chiFlag) {
        uint256 gasStart = gasleft();

        _;

        if ((chiFlag & 0x1) == 1) {
            uint256 gasSpent = 21000 + 16 * msg.data.length + gasStart - gasleft();
            uint256 freeUpValue = (gasSpent + 9529) / 41947;

            chi.freeUpTo(freeUpValue);
        }
    }
}
