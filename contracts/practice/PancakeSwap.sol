// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import '../interfaces/common/IERC20.sol';
import '../libraries/TransferHelper.sol';
import '../libraries/Withdrawable.sol';
import '../libraries/uniswap_v2/PancakeswapLibrary.sol';


contract PancakeSwap is Withdrawable {
    address factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;

    function swapTokensForExactTokens(
        uint amountOut,
        uint amountInMax,
        address[] calldata path
    ) external returns (uint[] memory amounts) {
        address firstPair = PancakeswapLibrary.pairFor(factory, path[0], path[1]);
        IERC20(path[0]).approve(firstPair, amountInMax);

        amounts = PancakeswapLibrary.getAmountsIn(factory, amountOut, path);
        require(amounts[0] <= amountInMax);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _swap(amounts, path);
    }

    function _swap(uint[] memory amounts, address[] memory path) internal virtual {
        for (uint i; i < path.length - 1; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = PancakeswapLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = i < path.length - 2 ? PancakeswapLibrary.pairFor(factory, output, path[i + 2]) : address(this);
            IUniswapV2Pair(PancakeswapLibrary.pairFor(factory, input, output)).swap(
                amount0Out, amount1Out, to, new bytes(0)
            );
        }
    }
}
