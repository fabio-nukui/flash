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


contract PcsPcs2V1 is Withdrawable, CHIBurner {
    address constant pcs1Factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    address constant pcs2Factory = 0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73;
    bytes32 constant initCodeHash1 = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    bytes32 constant initCodeHash2 = hex'00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5';
    uint256 constant pcs1Fee = 20;
    uint256 constant pcs2Fee = 25;
    uint8 constant PCS_1_FIRST = 0;
    uint8 constant PCS_2_FIRST = 1;

    // PcsV1 first
    function swapPcs1First(
        address[] calldata path,
        uint256 amountLast
    ) external discountCHIOn restricted {
        address pcs1Pair = PancakeswapLibrary.pairFor(pcs1Factory, initCodeHash1, path[path.length - 2], path[path.length - 1]);
        (address token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encodeWithHeader(PCS_1_FIRST, path);
        IUniswapV2Pair(pcs1Pair).swap(amount0Out, amount1Out, address(this), data);
    }

    // PcsV2 first
    function swapPcs2First(
        address[] calldata path,
        uint256 amountLast
    ) external discountCHIOn restricted {
        address pcs2Pair = PancakeswapLibrary.pairFor(pcs2Factory, initCodeHash2, path[path.length - 2], path[path.length - 1]);
        (address token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encodeWithHeader(PCS_2_FIRST, path);
        IUniswapV2Pair(pcs2Pair).swap(amount0Out, amount1Out, address(this), data);
    }

    function pancakeCall(
        address,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external {
        (uint8 mode, address[] memory path) = AddressArrayEncoder.decodeWithHeader(data);
        uint256 amountSendPair = amount0 == 0 ? amount1 : amount0;

        (address firstFactory, address secondFactory) = mode == PCS_1_FIRST ? (pcs1Factory, pcs2Factory) : (pcs2Factory, pcs1Factory);
        (bytes32 firstHash, bytes32 secondHash) = mode == PCS_1_FIRST ? (initCodeHash1, initCodeHash2) : (initCodeHash2, initCodeHash1);
        (uint256 firstFee, uint256 secondFee) = mode == PCS_1_FIRST ? (pcs1Fee, pcs2Fee) : (pcs2Fee, pcs1Fee);

        uint256[] memory amounts = PancakeswapLibrary.getAmountsIn(firstFactory, firstHash, amountSendPair, path, firstFee);
        exchangePcs(secondFactory, secondHash, secondFee, path[path.length - 1], path[0], amountSendPair, amounts[0]);

        address firstPair = PancakeswapLibrary.pairFor(firstFactory, firstHash, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _pcs_swap(firstFactory, firstHash, amounts, path);
    }

    function exchangePcs(
        address factory,
        bytes32 initCodeHash,
        uint256 fee,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin
    ) internal {
        address pairAddress = PancakeswapLibrary.pairFor(factory, initCodeHash, tokenIn, tokenOut);
        IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);

        (uint reserveIn, uint reserveOut) = PancakeswapLibrary.getPairReserves(pairAddress, tokenIn, tokenOut);
        uint256 amountOut = PancakeswapLibrary.getAmountOut(amountIn, reserveIn, reserveOut, fee);
        require(amountOut > amountOutMin, 'PCS low return');
        TransferHelper.safeApproveAndTransfer(tokenIn, pairAddress, amountIn);

        (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
        pair.swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _pcs_swap(address factory, bytes32 initCodeHash, uint[] memory amounts, address[] memory path) internal {
        for (uint i; i < path.length - 2; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = PancakeswapLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = PancakeswapLibrary.pairFor(factory, initCodeHash, output, path[i + 2]);
            address from = PancakeswapLibrary.pairFor(factory, initCodeHash, input, output);
            IUniswapV2Pair(from).swap(amount0Out, amount1Out, to, new bytes(0));
        }
    }
}
