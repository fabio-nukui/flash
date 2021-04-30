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
    address constant pcsFactory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    bytes32 constant cakeInitCodeHash = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    uint32 constant pcsFee = 20;

    // MDX first
    function swapMdxFirst(
        address[] calldata path,
        uint256 amountLast
    ) external discountCHIOn restricted {
        address mdxPair = MdexLibrary.pairFor(path[path.length - 2], path[path.length - 1]);
        (address token0, ) = MdexLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encode(path);
        IUniswapV2Pair(mdxPair).swap(
            amount0Out,
            amount1Out,
            address(this),
            data
        );
    }

    function swapV2Call(
        address,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external {
        address[] memory path = AddressArrayEncoder.decode(data);
        uint256 amountSendPcs = amount0 == 0 ? amount1 : amount0;

        uint256[] memory amounts = MdexLibrary.getAmountsIn(amountSendPcs, path);
        exchangePcs(path[path.length - 1], path[0], amountSendPcs, amounts[0]);

        address firstPair = MdexLibrary.pairFor(path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _mdx_swap(amounts, path);
    }

    function exchangePcs(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin
    ) private {
        address pairAddress = PancakeswapLibrary.pairFor(pcsFactory,cakeInitCodeHash, tokenIn, tokenOut);
        IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);

        (uint reserveIn, uint reserveOut) = PancakeswapLibrary.getReserves(pcsFactory, cakeInitCodeHash, tokenIn, tokenOut);
        uint256 amountOut = PancakeswapLibrary.getAmountOut(amountIn, reserveIn, reserveOut, pcsFee);
        require(amountOut > amountOutMin, 'PCS low return');
        TransferHelper.safeApproveAndTransfer(tokenIn, pairAddress, amountIn);

        (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
        pair.swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _mdx_swap(uint[] memory amounts, address[] memory path) internal {
        for (uint i; i < path.length - 2; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = MdexLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = MdexLibrary.pairFor(output, path[i + 2]);
            IUniswapV2Pair(MdexLibrary.pairFor(input, output)).swap(amount0Out, amount1Out, to, new bytes(0));
        }
    }

    // Pcs first
    function swapPcsFirst(
        address[] calldata path,
        uint256 amountLast
    ) external discountCHIOn restricted {
        address pcsPair = PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, path[path.length - 2], path[path.length - 1]);
        (address token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        uint256 amount0Out = token0 == path[path.length - 1] ? amountLast : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amountLast;

        bytes memory data = AddressArrayEncoder.encode(path);
        IUniswapV2Pair(pcsPair).swap(
            amount0Out,
            amount1Out,
            address(this),
            data
        );
    }

    function pancakeCall(
        address,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external {
        address[] memory path = AddressArrayEncoder.decode(data);
        uint256 amountSendMdx = amount0 == 0 ? amount1 : amount0;

        uint256[] memory amounts = PancakeswapLibrary.getAmountsIn(pcsFactory, cakeInitCodeHash, amountSendMdx, path, pcsFee);
        exchangeMdx(path[path.length - 1], path[0], amountSendMdx, amounts[0]);

        address firstPair = PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _pcs_swap(amounts, path);
    }

    function exchangeMdx(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin
    ) private {
        address pairAddress = MdexLibrary.pairFor(tokenIn, tokenOut);
        IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);

        (uint reserveIn, uint reserveOut) = MdexLibrary.getReserves(pairAddress, tokenIn, tokenOut);
        uint256 fee = MdexLibrary.getPairFees(pairAddress);
        uint256 amountOut = MdexLibrary.getAmountOut(amountIn, reserveIn, reserveOut, fee);
        require(amountOut > amountOutMin, 'MDX low return');
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
            IUniswapV2Pair(PancakeswapLibrary.pairFor(pcsFactory, cakeInitCodeHash, input, output)).swap(amount0Out, amount1Out, to, new bytes(0));
        }
    }
}
