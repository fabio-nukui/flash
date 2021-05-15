// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../libraries/CHIBurner.sol";

import {PancakeswapLibrary} from "../libraries/uniswap_v2/PancakeswapLibrary.sol";


contract MultiV1 is Withdrawable, CHIBurner {
    uint256 constant _DEX0_MASK =        0x3e00000000000000000000000000000000000000000000000000000000000000;
    uint256 constant _DEX1_MASK =        0x01f0000000000000000000000000000000000000000000000000000000000000;
    uint256 constant _AMOUNT_EXP_MASK =  0x000fc00000000000000000000000000000000000000000000000000000000000;
    uint256 constant _AMOUNT_MANT_MASK = 0x00003fff00000000000000000000000000000000000000000000000000000000;
    uint256 constant _ADDR_0_MASK =      0x00000000ffffffffffffffffffffffffffffffffffffffff0000000000000000;
    uint256 constant _ADDR_1_MASK_0 =    0x000000000000000000000000000000000000000000000000ffffffffffffffff;
    uint256 constant _ADDR_1_MASK_1 =    0xffffffffffffffffffffffff0000000000000000000000000000000000000000;
    uint256 constant _ADDR_2_MASK =      0x000000000000000000000000ffffffffffffffffffffffffffffffffffffffff;
    uint256 constant _ADDR_3_MASK =      0xffffffffffffffffffffffffffffffffffffffff000000000000000000000000;

    uint256 constant _PAIR_FOR_MASK_0 = 0x000000000000000000000000000000000000000000000ffffffffffffffffffff;
    uint256 constant _PAIR_FOR_MASK_1 = 0x000000000000000000000000fffffffffffffffffffff000000000000000000000;

    uint256 constant _UNIV2PAIR_RESERVES_SELECTOR_32 = 0x0902f1ac00000000000000000000000000000000000000000000000000000000;
    bytes32 constant initCodeHashPcs1 = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    bytes32 constant initCodeHashPcs2 = hex'00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5';
    bytes32 constant initCodeHashMdex = hex'0d994d996174b05cfc7bed897dc1b20b4c458fc8d64fe98bc78b3c64a6b4d093';
    uint256 constant pcs1Fee = 20;
    uint256 constant pcs2Fee = 25;
    uint256 constant PCS_1 = 0;
    uint256 constant PCS_2 = 1;
    uint256 constant MDEX = 2;
    address constant pcs1Factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    address constant pcs2Factory = 0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73;
    address constant mdexFactory = 0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8;
    address constant WBNB = 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c;

    // function _decodeFlash(
    //     bytes calldata
    // ) internal pure returns(uint256 dex0, uint256 dex1, uint256 amountLast, address[] memory pairs) {
    //     assembly {
    //         let n := calldataload(0x0)
    //         let data0 := calldataload(0x20)
    //         let data1 := calldataload(0x40)
    //         dex0 := shr(250, and(data0, _DEX0_MASK))
    //         dex1 := shr(244, and(data0, _DEX1_MASK))

    //         let amountExp := shr(238, and(data0, _AMOUNT_EXP_MASK))
    //         let amountMant := shr(224, and(data0, _AMOUNT_MANT_MASK))
    //         amountLast := shl(add(amountExp, 6), amountMant)

    //         mstore(add(pairs, 0x20), shr(64, and(data0, _TOKEN_0_MASK)))
    //         mstore(add(pairs, 0x40), add(shl(96, and(data0, _TOKEN_1_MASK_0)), shr(160, and(data1, _TOKEN_1_MASK_1))))
    //         let token_2 := and(data1, _TOKEN_2_MASK)
    //         switch iszero(token_2)
    //         case 1 {
    //             mstore(path, 3)
    //             mstore(add(path, 0x60), WBNB)
    //             mstore(0x40, add(path, 0x80))  // Update free memory pointer
    //         }
    //         default {
    //             mstore(path, 4)
    //             mstore(add(path, 0x60), token_2)
    //             mstore(add(path, 0x80), WBNB)
    //             mstore(0x40, add(path, 0xa0))  // Update free memory pointer
    //         }
    //     }
    //     assembly {
    //         dex0 := mload(add(data_, 1))
    //         dex1 := mload(add(data_, 2))
    //         let n := div(mload(data_), 20)  // n = data.length / 20
    //         mstore(addresses, n)  // addresses = new addresses[](n)
    //         for { let i := 0 } lt(i, n) { i := add(i, 1) } {  // for (uint i = 0; i < n; i++)
    //             mstore(add(addresses, add(32, mul(i, 32))), mload(add(data_, add(22, mul(i, 20)))))  // addresses[i] = data[i * 20 + 2:(i + 1) * 20 + 2]
    //         }
    //     }
    // }

    // function flash_09lc(  // 0x00000d86
    //     bytes calldata data
    // ) external discountCHIOn restricted {
    //     (,uint256 dex1, address[] memory path) = _decodeFlash(data);
    //     address pcs1Pair;
    //     address token0;
    //     {  // Scope to avoid stack too deep error
    //     (address firstFactory, bytes32 firstHash) = dex1 == PCS_1 ? (pcs1Factory, initCodeHash1) : (pcs2Factory, initCodeHash2);
    //     pcs1Pair = PancakeswapLibrary.pairFor(firstFactory, firstHash, path[path.length - 2], path[path.length - 1]);
    //     (token0, ) = PancakeswapLibrary.sortTokens(path[path.length - 2], path[path.length - 1]);
    //     }
    //     uint256 amount0Out = token0 == path[path.length - 1] ? amount : 0;
    //     uint256 amount1Out = token0 == path[path.length - 1] ? 0 : amount;
    //     IUniswapV2Pair(pcs1Pair).swap(amount0Out, amount1Out, address(this), data);
    // }

    // function pancakeCall(
    //     address,
    //     uint256 amount0,
    //     uint256 amount1,
    //     bytes calldata data
    // ) external {
    //     (uint256 dex0, uint256 dex1, address[] memory path) = _decodeFlash(data);
    //     uint256 amountSendPair = amount0 == 0 ? amount1 : amount0;

    //     (address factory0, bytes32 hash_0, uint256 fee0) =
    //         dex0 == PCS_1
    //             ? (pcs1Factory, initCodeHash1, pcs1Fee)
    //             : (pcs2Factory, initCodeHash2, pcs2Fee);
    //     (address factory1, bytes32 hash_1, uint256 fee1) =
    //         dex1 == PCS_1
    //             ? (pcs1Factory, initCodeHash1, pcs1Fee)
    //             : (pcs2Factory, initCodeHash2, pcs2Fee);

    //     uint256[] memory amounts = PancakeswapLibrary.getAmountsIn(factory1, hash_1, amountSendPair, path, fee1);
    //     exchangePcs(factory0, hash_0, fee0, path[path.length - 1], path[0], amountSendPair, amounts[0]);

    //     address firstPair = PancakeswapLibrary.pairFor(factory1, hash_1, path[0], path[1]);
    //     TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
    //     _pcs_swap(factory1, hash_1, amounts, path);
    // }

    // function exchangePcs(
    //     address factory,
    //     bytes32 initCodeHash,
    //     uint256 fee,
    //     address tokenIn,
    //     address tokenOut,
    //     uint256 amountIn,
    //     uint256 amountOutMin
    // ) internal {
    //     address pairAddress = PancakeswapLibrary.pairFor(factory, initCodeHash, tokenIn, tokenOut);
    //     IUniswapV2Pair pair = IUniswapV2Pair(pairAddress);

    //     (uint reserveIn, uint reserveOut) = PancakeswapLibrary.getPairReserves(pairAddress, tokenIn, tokenOut);
    //     uint256 amountOut = PancakeswapLibrary.getAmountOut(amountIn, reserveIn, reserveOut, fee);
    //     require(amountOut > amountOutMin, 'LR');
    //     TransferHelper.safeTransfer(tokenIn, pairAddress, amountIn);

    //     (uint256 amount0Out, uint256 amount1Out) = tokenIn == pair.token0() ? (uint(0), amountOut) : (amountOut, uint(0));
    //     pair.swap(amount0Out, amount1Out, address(this), new bytes(0));
    // }

    // function _pcs_swap(address factory, bytes32 initCodeHash, uint[] memory amounts, address[] memory path) internal {
    //     for (uint i; i < path.length - 2; i++) {
    //         (address input, address output) = (path[i], path[i + 1]);
    //         (address token0,) = PancakeswapLibrary.sortTokens(input, output);
    //         uint amountOut = amounts[i + 1];
    //         (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
    //         address to = PancakeswapLibrary.pairFor(factory, initCodeHash, output, path[i + 2]);
    //         address from = PancakeswapLibrary.pairFor(factory, initCodeHash, input, output);
    //         IUniswapV2Pair(from).swap(amount0Out, amount1Out, to, new bytes(0));
    //     }
    // }

    function uint2str(uint _i) internal pure returns (string memory _uintAsString) {
        if (_i == 0) {
            return "0";
        }
        uint j = _i;
        uint len;
        while (j != 0) {
            len++;
            j /= 10;
        }
        bytes memory bstr = new bytes(len);
        uint k = len - 1;
        while (_i != 0) {
            bstr[k--] = byte(uint8(48 + _i % 10));
            _i /= 10;
        }
        return string(bstr);
    }

    function swap32_bZf(  // 0x000019e2
        bytes32 data
    ) external discountCHIOn restricted {
        uint256 amountLast;
        bytes32 amountIn0;
        uint256 amountIn1;
        address token;
        address pair0;
        address pair1;
        // Data has structure {uint2 reserved}{uint5 dex0}{uint5 dex1}{uint6 amountExp}{uint14 amountMant}{bytes20 token}
        assembly {
            function pairFor(ptr, tokenA, tokenB, dex) -> ret {
                // switch lt(tokenA, tokenB)
                // case 1 {
                    // mstore(ptr, add(shl(96, tokenA), shr(80, and(tokenB, _PAIR_FOR_MASK_1))))
                //     mstore(add(ptr, 0x20), shl(22, and(tokenB, _PAIR_FOR_MASK_0)))
                // }
                // default {
                //     mstore(ptr, add(shl(96, tokenB), shr(80, and(tokenA, _PAIR_FOR_MASK_1))))
                //     mstore(add(ptr, 0x20), shl(22, and(tokenA, _PAIR_FOR_MASK_0)))
                // }
                mstore(ptr, add(shl(96, tokenA), shr(80, and(tokenB, _PAIR_FOR_MASK_1))))
                ret := keccak256(ptr, 32)
            }
            let ptr := mload(0x40)

            let dex0 := shr(249, and(data, _DEX0_MASK))
            let dex1 := shr(244, and(data, _DEX1_MASK))
            {
            let amountExp := shr(238, and(data, _AMOUNT_EXP_MASK))
            let amountMant := shr(224, and(data, _AMOUNT_MANT_MASK))
            amountLast := shl(amountExp, amountMant)
            }

            token := shr(64, and(data, _ADDR_0_MASK))
            amountIn0 := pairFor(ptr, token, WBNB, dex0)
        }
        // require(false, uint2str(amountIn0));
        require(false, string(abi.encodePacked(amountIn0)));

        (address token0,) = PancakeswapLibrary.sortTokens(WBNB, token);

        (uint256 amount0Out, uint256 amount1Out) = token0 == WBNB ? (uint(0), amountIn1) : (amountIn1, uint(0));
        IUniswapV2Pair(pair0).swap(amount0Out, amount1Out, pair1, new bytes(0));

        (amount0Out, amount1Out) = token0 == WBNB ? (amountLast, uint(0)) : (uint(0), amountLast);
        IUniswapV2Pair(pair1).swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    // function _get_pairs_amounts32(
    //     uint8 dex0,
    //     uint8 dex1,
    //     address token,
    //     uint256 amountLast
    // ) internal view returns(address pair0, address pair1, uint256 amountIn0, uint256 amountIn1) {
    //     {  // scope to avoid stack too deep errors
    //     (address factory1, bytes32 hash_1, uint256 fee1) =
    //         dex1 == PCS_1
    //             ? (pcs1Factory, initCodeHash1, pcs1Fee)
    //             : (pcs2Factory, initCodeHash2, pcs2Fee);
    //     pair1 = PancakeswapLibrary.pairFor(factory1, hash_1, WBNB, token);
    //     (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(pair1, token, WBNB);
    //     amountIn1 = PancakeswapLibrary.getAmountIn(amountLast, reserveIn, reserveOut, fee1);
    //     }
    //     (address factory0, bytes32 hash_0, uint256 fee0) =
    //         dex0 == PCS_1
    //             ? (pcs1Factory, initCodeHash1, pcs1Fee)
    //             : (pcs2Factory, initCodeHash2, pcs2Fee);
    //     pair0 = PancakeswapLibrary.pairFor(factory0, hash_0, WBNB, token);
    //     (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(pair0, WBNB, token);
    //     amountIn0 = PancakeswapLibrary.getAmountIn(amountIn1, reserveIn, reserveOut, fee0);

    //     require(amountIn0 < amountLast, 'LR');
    // }

    function _get_amounts(
        uint256 dex0,
        uint256 dex1,
        uint256 amountLast,
        address firstPair,
        address[] memory pairs,
        address[] memory path
    ) internal view returns(uint256 amountFirst, uint256[] memory amounts) {
        uint256 fee = dex1 == PCS_1 ? pcs1Fee : pcs2Fee;
        amounts = PancakeswapLibrary.getAmountsInPairs(amountLast, path, pairs, fee);

        fee = dex0 == PCS_1 ? pcs1Fee : pcs2Fee;
        (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(firstPair, WBNB, path[0]);
        amountFirst = PancakeswapLibrary.getAmountIn(amounts[0], reserveIn, reserveOut, fee);

        require(amountFirst < amountLast, 'LR');
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
