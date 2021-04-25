// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../libraries/CHIBurner.sol";
import "../libraries/AddressArrayEncoder.sol";

import "../interfaces/common/IERC20.sol";
import {PancakeswapLibrary} from "../libraries/uniswap_v2/PancakeswapLibrary.sol";
import {MdexLibrary} from "../libraries/uniswap_v2/MdexLibrary.sol";


contract PcsMdxV1 is Withdrawable, CHIBurner {
    address constant pcs1Factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    address constant pcs2Factory = 0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73;
    bytes constant PCS_1_FIRST = 0;
    bytes constant PCS_2_FIRST = 1;

    // PcsV1 first
    function swapPcs1First(
        address[] calldata path,
        uint256 amountLast
    ) external discountCHIOn restricted {
        address pcs1Pair = PancakeswapLibrary.pairFor(pcs1Factory, path[path.length - 2], path[path.length - 1]);
        (address token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encode_with_header(PCS_1_FIRST, path);
        IUniswapV2Pair(pcs1Pair).swap(amount0Out, amount1Out, address(this), data);
    }

    // PcsV2 first
    function swapPcs2First(
        address[] calldata path,
        uint256 amountLast
    ) external discountCHIOn restricted {
        address pcs2Pair = PancakeswapLibrary.pairFor(pcs2Factory, path[path.length - 2], path[path.length - 1]);
        (address token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encode_with_header(PCS_2_FIRST, path);
        IUniswapV2Pair(pcs2Pair).swap(amount0Out, amount1Out, address(this), data);
    }

    function pancakeCall(
        address sender,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external {
        address[] memory path = AddressArrayEncoder.decode(data);
        uint256 amountSendPcs2 = amount0 == 0 ? amount1 : amount0;

        uint256[] memory amounts = PancakeswapLibrary.getAmountsIn(pcsFactory, amountSendPcs2, path);
        exchangePcs(path[path.length - 1], path[0], amountSendPcs2, amounts[0]);

        address firstPair = PancakeswapLibrary.pairFor(pcsFactory, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _pcs_swap(amounts, path);
    }

    function exchangePcs(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin
    ) private {
        address pairAddress = PancakeswapLibrary.pairFor(pcsFactory, tokenIn, tokenOut);
        IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);

        (uint reserveIn, uint reserveOut) = PancakeswapLibrary.getReserves(pcsFactory, tokenIn, tokenOut);
        uint256 amountOut = PancakeswapLibrary.getAmountOut(amountIn, reserveIn, reserveOut);
        require(amountOut > amountOutMin, 'PCS low return');
        TransferHelper.safeApproveAndTransfer(tokenIn, pairAddress, amountIn);

        (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
        pair.swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _pcs_swap(uint[] memory amounts, address[] memory path) internal {
        for (uint i; i < path.length - 2; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = PancakeswapLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = PancakeswapLibrary.pairFor(pcsFactory, output, path[i + 2]);
            IUniswapV2Pair(PancakeswapLibrary.pairFor(pcsFactory, input, output)).swap(amount0Out, amount1Out, to, new bytes(0));
        }
    }
}
