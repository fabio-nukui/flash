// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../libraries/CHIBurner.sol";
import "../libraries/AddressArrayEncoder.sol";

import "../interfaces/common/IERC20.sol";
import "../interfaces/valuedefiswap/IValueLiquidPair.sol";
import {PancakeswapLibrary} from "../libraries/uniswap_v2/PancakeswapLibrary.sol";
import "../interfaces/uniswap_v2/IPancakeCallee.sol";
import "../interfaces/valuedefiswap/IValueLiquidFormula.sol";
import "../interfaces/valuedefiswap/IValueLiquidPair.sol";


contract PcsVdsV1 is IPancakeCallee, Withdrawable, CHIBurner {
    address constant pcsFactory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    address constant vdsFormula = 0x45f24BaEef268BB6d63AEe5129015d69702BCDfa;

    // // VDS first
    // function swapVdsFirst(
    //     address tokenFirst,
    //     address tokenLast,
    //     uint256 amountLast,
    //     address[] calldata midPath,
    //     uint8 chiFlag
    // ) external discountCHI(chiFlag) restricted {

    // }

    // function exchangePcs(
    //     address pairAddress,
    //     address tokenIn,
    //     uint256 amountIn
    // ) private {
    //     IValueLiquidPair pair = IValueLiquidPair(pairAddress);
    //     IValueLiquidFormula formula = IValueLiquidFormula(vdsFormula);

    //     uint256 amountOut = formula.getPairAmountOut(pairAddress, tokenIn, amountIn);
    //     TransferHelper.safeTransfer(tokenIn, pairAddress, amountIn);

    //     (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
    //     pair.swap(amount0Out, amount1Out, this.address, bytes(0));
    // }

    // function uniswapV2Call(
    //     address sender,
    //     uint256 amount0,
    //     uint256 amount1,
    //     bytes calldata data
    // ) external override {
    // }

    // function _vds_swap(uint[] memory amounts, address[] memory path) internal virtual {
    // }

    // Pcs first
    function swapPcsFirst(
        address tokenFirst,
        address tokenLast,
        uint256 amountLast,
        address[] calldata midPath, // Fist address is Vds pair
        uint8 chiFlag
    ) external discountCHI(chiFlag) restricted {
        address pcsPair = PancakeswapLibrary.pairFor(pcsFactory, tokenFirst, tokenLast);
        (address tokenA, ) = PancakeswapLibrary.sortTokens(tokenFirst, tokenLast);
        uint256 amountAOut = tokenA == tokenLast ? amountLast : 0;
        uint256 amountBOut = tokenA == tokenLast ? 0 : amountLast;

        IUniswapV2Pair(pcsPair).swap(
            amountAOut,
            amountBOut,
            address(this),
            AddressArrayEncoder.encode(midPath)
        );
    }

    function pancakeCall(
        address sender,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external override {
        address[] memory midPath = AddressArrayEncoder.decode(data); // Fist address is Vds pair
        address vdsPair = midPath[0];
        uint256 amountSendVds = amount0 == 0 ? amount1 : amount0;
        address[] memory path;
        if (midPath.length > 1) {
            path = new address[](1 + midPath.length);
            for (uint i; i < midPath.length - 1; i++) {
                path[i + 1] = midPath[i + 1];
            }
        } else {
            path = new address[](2);
        }
        uint256[] memory amounts;
        { // scope for token{0,1}, avoids stack too deep errors
        address token0 = IUniswapV2Pair(msg.sender).token0();
        address token1 = IUniswapV2Pair(msg.sender).token1();
        require(msg.sender == PancakeswapLibrary.pairFor(pcsFactory, token0, token1)); // ensure that msg.sender is actually a V2 pair
        path[0] = amount0 == 0 ? token0 : token1;
        path[path.length - 1] = amount0 == 0 ? token1 : token0;
        amounts = PancakeswapLibrary.getAmountsIn(pcsFactory, amountSendVds, path);
        }
        TransferHelper.safeApprove(path[path.length - 1], vdsPair, amountSendVds);
        exchangeVds(vdsPair, path[path.length - 1], amountSendVds);

        address firstPair = PancakeswapLibrary.pairFor(pcsFactory, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _pcs_swap(amounts, path);
    }

    function exchangeVds(
        address pairAddress,
        address tokenIn,
        uint256 amountIn
    ) private {
        IValueLiquidPair pair = IValueLiquidPair(pairAddress);
        IValueLiquidFormula formula = IValueLiquidFormula(vdsFormula);

        uint256 amountOut = formula.getPairAmountOut(pairAddress, tokenIn, amountIn);
        TransferHelper.safeTransfer(tokenIn, pairAddress, amountIn);

        (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
        pair.swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _pcs_swap(uint[] memory amounts, address[] memory path) internal virtual {
        for (uint i; i < path.length - 2; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = PancakeswapLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = PancakeswapLibrary.pairFor(pcsFactory, output, path[i + 2]);
            IUniswapV2Pair(PancakeswapLibrary.pairFor(pcsFactory, input, output)).swap(
                amount0Out, amount1Out, to, new bytes(0)
            );
        }
    }
}
