// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../libraries/CHIBurner.sol";
import "../libraries/AddressArrayEncoder.sol";

import "../interfaces/common/IERC20.sol";
import {PancakeswapLibrary} from "../libraries/uniswap_v2/PancakeswapLibrary.sol";
import "../interfaces/uniswap_v2/IPancakeCallee.sol";
import "../interfaces/valuedefiswap/IValueLiquidFormula.sol";
import "../interfaces/valuedefiswap/IValueLiquidPair.sol";
import "../interfaces/valuedefiswap/IValueLiquidFactory.sol";


contract PcsVdsV1 is IPancakeCallee, Withdrawable, CHIBurner {
    address constant pcsFactory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    bytes32 constant cakeInitCodeHash = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    uint32 constant pcsFee = 20;
    address constant vdsFactory = 0x1B8E12F839BD4e73A47adDF76cF7F0097d74c14C;
    address constant vdsFormula = 0x45f24BaEef268BB6d63AEe5129015d69702BCDfa;

    // VDS first
    function swapVdsFirst(  // gas cost w/o CHI: 1 hop: 204_541; 2 hops: 286_760
        address[] calldata path, // First address is tokenFirst, second address is tokenLast
        uint256 amountLast,
        uint8 chiFlag
    ) external discountCHI(chiFlag) restricted {
        IValueLiquidPair lastPair = IValueLiquidPair(path[path.length - 1]);
        uint256 amount0Out;
        uint256 amount1Out;
        { // scope for tokenLast; token0, avoids stack too deep errors
        address tokenLast = path[1];
        address token0 = lastPair.token0();
        amount0Out = token0 == tokenLast ? amountLast : 0;
        amount1Out = token0 == tokenLast ? 0 : amountLast;
        }

        bytes memory data = AddressArrayEncoder.encode(path[:path.length - 1]);
        lastPair.swap(amount0Out, amount1Out, address(this), data);
    }

    function uniswapV2Call(
        address sender,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external {
        require(IValueLiquidFactory(vdsFactory).isPair(msg.sender)); // ensure that msg.sender is actually a VDS pair

        address[] memory pairPath = AddressArrayEncoder.decode(data);

        address tokenFirst = pairPath[0];
        address tokenLast = pairPath[1];
        address pcsPair = PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, tokenFirst, tokenLast);
        uint256 amountSendPcs = amount0 == 0 ? amount1 : amount0;

        address[] memory path = new address[](pairPath.length - 1);
        for (uint i; i < path.length - 1; i++) {
            path[i] = pairPath[i + 2];
        }
        path[path.length - 1] = msg.sender;

        uint256[] memory amounts = IValueLiquidFormula(vdsFormula).getAmountsIn(tokenFirst, tokenLast, amountSendPcs, path);
        exchangePcs(pcsPair, tokenLast, tokenFirst, amountSendPcs, amounts[0]);

        TransferHelper.safeTransfer(tokenFirst, path[0], amounts[0]);
        _vds_swap(tokenFirst, amounts, path);
    }

    function exchangePcs(
        address pairAddress,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin
    ) private {
        IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);

        (uint reserveIn, uint reserveOut) = PancakeswapLibrary.getReserves(pcsFactory, cakeInitCodeHash, tokenIn, tokenOut);
        uint256 amountOut = PancakeswapLibrary.getAmountOut(amountIn, reserveIn, reserveOut, pcsFee);
        require(amountOut > amountOutMin, 'PCS low return');
        TransferHelper.safeApproveAndTransfer(tokenIn, pairAddress, amountIn);

        (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
        pair.swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _vds_swap(
        address tokenIn,
        uint256[] memory amounts,
        address[] memory path
    ) internal {
        address input = tokenIn;
        for (uint i; i < path.length - 1; i++) {
            IValueLiquidPair pair = IValueLiquidPair(path[i]);
            address token0 = pair.token0();
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out, address output) = input == token0 ? (uint(0), amountOut, pair.token1()) : (amountOut, uint(0), token0);
            address to = path[i + 1];
            pair.swap(amount0Out, amount1Out, to, new bytes(0));
            input = output;
        }
    }

    // Pcs first
    function swapPcsFirst(  // gas cost w/o CHI: 1 hop: 204_776; 2 hops: 267_456; 3 hops: 338_507
        address[] calldata path, // Fist address is Vds pair
        uint256 amountLast,
        uint8 chiFlag
    ) external discountCHI(chiFlag) restricted {
        address pcsPair = PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, path[path.length - 2], path[path.length - 1]);
        (address token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encode(path[:path.length - 2]);
        IUniswapV2Pair(pcsPair).swap(
            amount0Out,
            amount1Out,
            address(this),
            data
        );
    }

    function pancakeCall(
        address sender,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external override {
        address[] memory pathStart = AddressArrayEncoder.decode(data);
        address vdsPair = pathStart[0];
        uint256 amountSendVds = amount0 == 0 ? amount1 : amount0;

        address[] memory path = new address[](pathStart.length + 1);
        for (uint i; i < pathStart.length - 1; i++) {
            path[i] = pathStart[i + 1];
        }

        uint256[] memory amounts;
        { // scope for token{0,1}, avoids stack too deep errors
        address token0 = IUniswapV2Pair(msg.sender).token0();
        address token1 = IUniswapV2Pair(msg.sender).token1();
        require(msg.sender == PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, token0, token1)); // ensure that msg.sender is actually a V2 pair
        path[path.length - 2] = amount0 == 0 ? token0 : token1;
        path[path.length - 1] = amount0 == 0 ? token1 : token0;
        amounts = PancakeswapLibrary.getAmountsIn(pcsFactory, cakeInitCodeHash, amountSendVds, path, pcsFee);
        }
        exchangeVds(vdsPair, path[path.length - 1], amountSendVds, amounts[0]);

        address firstPair = PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _pcs_swap(amounts, path);
    }

    function exchangeVds(
        address pairAddress,
        address tokenIn,
        uint256 amountIn,
        uint256 amountOutMin
    ) private {
        IValueLiquidPair pair = IValueLiquidPair(pairAddress);
        IValueLiquidFormula formula = IValueLiquidFormula(vdsFormula);

        uint256 amountOut = formula.getPairAmountOut(pairAddress, tokenIn, amountIn);
        require(amountOut > amountOutMin, 'VDS low return');
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
            address to = PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, output, path[i + 2]);
            IUniswapV2Pair(PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, input, output)).swap(
                amount0Out, amount1Out, to, new bytes(0)
            );
        }
    }
}
