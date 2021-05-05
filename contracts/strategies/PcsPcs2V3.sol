// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../libraries/CHIBurner.sol";
import "../libraries/AddressArrayEncoder.sol";

import "../interfaces/common/IERC20.sol";
import {PancakeswapLibrary} from "../libraries/uniswap_v2/PancakeswapLibrary.sol";


contract PcsPcs2V3 is Withdrawable, CHIBurner {
    uint256 constant _DEX0_MASK =        0xfc00000000000000000000000000000000000000000000000000000000000000;
    uint256 constant _DEX1_MASK =        0x03f0000000000000000000000000000000000000000000000000000000000000;
    uint256 constant _AMOUNT_EXP_MASK =  0x000fc00000000000000000000000000000000000000000000000000000000000;
    uint256 constant _AMOUNT_MANT_MASK = 0x00003fff00000000000000000000000000000000000000000000000000000000;
    uint256 constant _TOKEN_0_MASK =     0x00000000ffffffffffffffffffffffffffffffffffffffff0000000000000000;
    uint256 constant _TOKEN_1_MASK_0 =   0x000000000000000000000000000000000000000000000000ffffffffffffffff;
    uint256 constant _TOKEN_1_MASK_1 =   0xffffffffffffffffffffffff0000000000000000000000000000000000000000;
    uint256 constant _TOKEN_2_MASK =     0x000000000000000000000000ffffffffffffffffffffffffffffffffffffffff;

    bytes32 constant initCodeHash1 = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    bytes32 constant initCodeHash2 = hex'00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5';
    uint256 constant pcs1Fee = 20;
    uint256 constant pcs2Fee = 25;
    address constant pcs1Factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    address constant pcs2Factory = 0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73;
    address constant WBNB = 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c;
    uint8 constant PCS_1 = 0;
    uint8 constant PCS_2 = 1;

    function flash_09lc(  // 0x00000d86
        bytes calldata data,
        uint256 amount
    ) external discountCHIOn restricted {
        (,uint8 dex1, address[] memory path) = AddressArrayEncoder.decodeWithHeader2(data);
        address pcs1Pair;
        address token0;
        {  // Scope to avoid stack too deep error
        (address firstFactory, bytes32 firstHash) = dex1 == PCS_1 ? (pcs1Factory, initCodeHash1) : (pcs2Factory, initCodeHash2);
        pcs1Pair = PancakeswapLibrary.pairFor(firstFactory, firstHash, path[path.length - 2], path[path.length - 1]);
        (token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
        }
        uint256 amount0Out = token0 == path[path.length - 1] ? amount : 0;
        uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amount;
        IUniswapV2Pair(pcs1Pair).swap(amount0Out, amount1Out, address(this), data);
    }

    function pancakeCall(
        address,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external {
        (uint256 dex0, uint256 dex1, address[] memory path) = AddressArrayEncoder.decodeWithHeader2(data);
        uint256 amountSendPair = amount0 == 0 ? amount1 : amount0;

        (address factory0, bytes32 hash_0, uint256 fee0) =
            dex0 == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        (address factory1, bytes32 hash_1, uint256 fee1) =
            dex1 == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);

        uint256[] memory amounts = PancakeswapLibrary.getAmountsIn(factory1, hash_1, amountSendPair, path, fee1);
        exchangePcs(factory0, hash_0, fee0, path[path.length - 1], path[0], amountSendPair, amounts[0]);

        address firstPair = PancakeswapLibrary.pairFor(factory1, hash_1, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _pcs_swap(factory1, hash_1, amounts, path);
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
        require(amountOut > amountOutMin, 'LR');
        TransferHelper.safeTransfer(tokenIn, pairAddress, amountIn);

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

    function swap32_bZf(  // 0x000019e2
        bytes32 data
    ) external discountCHIOn restricted {
        uint256 amountLast;
        address token;
        uint8 dex0;
        uint8 dex1;
        // Data has structure {uint6 dex0}{uint6 dex1}{uint6 amountExp}{uint14 amountMant}{bytes20 token}
        assembly {
            dex0 := shr(250, and(data, _DEX0_MASK))
            dex1 := shr(244, and(data, _DEX1_MASK))

            let amountExp := shr(238, and(data, _AMOUNT_EXP_MASK))
            let amountMant := shr(224, and(data, _AMOUNT_MANT_MASK))
            amountLast := shl(add(amountExp, 6), amountMant)

            token := shr(64, and(data, _TOKEN_0_MASK))
        }
        (
            address pair0,
            address pair1,
            uint256 amountIn0,
            uint256 amountIn1
        ) = _get_pairs_amounts32(dex0, dex1, token, amountLast);
        TransferHelper.safeTransfer(WBNB, pair0, amountIn0);

        (address token0,) = PancakeswapLibrary.sortTokens(WBNB, token);

        (uint256 amount0Out, uint256 amount1Out) = token0 == WBNB ? (uint(0), amountIn1) : (amountIn1, uint(0));
        IUniswapV2Pair(pair0).swap(amount0Out, amount1Out, pair1, new bytes(0));

        (amount0Out, amount1Out) = token0 == WBNB ? (amountLast, uint(0)) : (uint(0), amountLast);
        IUniswapV2Pair(pair1).swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _get_pairs_amounts32(
        uint8 dex0,
        uint8 dex1,
        address token,
        uint256 amountLast
    ) internal view returns(address pair0, address pair1, uint256 amountIn0, uint256 amountIn1) {
        {  // scope to avoid stack too deep errors
        (address factory1, bytes32 hash_1, uint256 fee1) =
            dex1 == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        pair1 = PancakeswapLibrary.pairFor(factory1, hash_1, WBNB, token);
        (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(pair1, token, WBNB);
        amountIn1 = PancakeswapLibrary.getAmountIn(amountLast, reserveIn, reserveOut, fee1);
        }
        (address factory0, bytes32 hash_0, uint256 fee0) =
            dex0 == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        pair0 = PancakeswapLibrary.pairFor(factory0, hash_0, WBNB, token);
        (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(pair0, WBNB, token);
        amountIn0 = PancakeswapLibrary.getAmountIn(amountIn1, reserveIn, reserveOut, fee0);

        require(amountIn0 < amountLast, 'LR');
    }

    function swap64_Fi4(  // 0x00002189
        bytes32 data0,
        bytes32 data1
    ) external discountCHIOn restricted {
        uint256 amountLast;
        uint8 dex0;
        uint8 dex1;
        address[] memory path;
        // Data has structure {uint6 dex0}{uint6 dex1}{uint6 amountExp}{uint14 amountMant}{bytes20 token0}{bytes20 token1}{bytes20 token2}
        assembly {
            dex0 := shr(250, and(data0, _DEX0_MASK))
            dex1 := shr(244, and(data0, _DEX1_MASK))

            let amountExp := shr(238, and(data0, _AMOUNT_EXP_MASK))
            let amountMant := shr(224, and(data0, _AMOUNT_MANT_MASK))
            amountLast := shl(add(amountExp, 6), amountMant)

            mstore(add(path, 0x20), shr(64, and(data0, _TOKEN_0_MASK)))
            mstore(add(path, 0x40), add(shl(96, and(data0, _TOKEN_1_MASK_0)), shr(160, and(data1, _TOKEN_1_MASK_1))))
            let token_2 := and(data1, _TOKEN_2_MASK)
            switch iszero(token_2)
            case 1 {
                mstore(path, 3)
                mstore(add(path, 0x60), WBNB)
                mstore(0x40, add(path, 0x80))  // Update free memory pointer
            }
            default {
                mstore(path, 4)
                mstore(add(path, 0x60), token_2)
                mstore(add(path, 0x80), WBNB)
                mstore(0x40, add(path, 0xa0))  // Update free memory pointer
            }
        }
        (
            address pair0,
            uint256 amountIn0,
            uint256[] memory amounts,
            address[] memory pairs
        ) = _get_pairs_amounts64(dex0, dex1, amountLast, path);
        TransferHelper.safeTransfer(WBNB, pair0, amountIn0);
        (address token0,) = PancakeswapLibrary.sortTokens(WBNB, path[0]);

        (uint256 amount0Out, uint256 amount1Out) = token0 == WBNB ? (uint(0), amounts[0]) : (amounts[0], uint(0));
        IUniswapV2Pair(pair0).swap(amount0Out, amount1Out, pairs[0], new bytes(0));

        _pcs_swap(amounts, path, pairs);
    }

    function _get_pairs_amounts64(
        uint8 dex0,
        uint8 dex1,
        uint256 amountLast,
        address[] memory path
    ) internal view returns (address pair0, uint256 amountIn0, uint256[] memory amounts, address[] memory pairs) {
        {  // scope to avoid stack too deep errors
        (address factory1, bytes32 hash_1, uint256 fee1) =
            dex1 == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        pairs = PancakeswapLibrary.getPairs(factory1, hash_1, path);
        amounts = PancakeswapLibrary.getAmountsInPairs(amountLast, path, pairs, fee1);
        }
        (address factory0, bytes32 hash_0, uint256 fee0) =
            dex0 == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        pair0 = PancakeswapLibrary.pairFor(factory0, hash_0, WBNB, path[0]);
        (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(pair0, WBNB, path[0]);
        amountIn0 = PancakeswapLibrary.getAmountIn(amounts[0], reserveIn, reserveOut, fee0);

        require(amountIn0 < amountLast, 'LR');
    }

    function _pcs_swap(
        uint[] memory amounts,
        address[] memory path,
        address[] memory pairs
    ) internal {
        for (uint i; i < path.length - 1; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = PancakeswapLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = i == path.length - 2 ? address(this) : pairs[i + 1];
            IUniswapV2Pair(pairs[i]).swap(amount0Out, amount1Out, to, new bytes(0));
        }
    }
}
