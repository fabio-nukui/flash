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
    uint256 constant BNB_DENOMINATOR = 16;
    bytes32 constant initCodeHash1 = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    bytes32 constant initCodeHash2 = hex'00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5';
    uint256 constant pcs1Fee = 20;
    uint256 constant pcs2Fee = 25;
    address constant pcs1Factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    address constant pcs2Factory = 0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73;
    address constant WBNB = 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c;
    uint8 constant PCS_1 = 0;
    uint8 constant PCS_2 = 1;
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

    function swap32_0342(  // 0x00013991
        bytes32
    ) external discountCHIOn restricted {
        uint256 amountLast;
        address token;
        uint8 firstDex;
        uint8 secondDex;
        uint80 tmpAmount;
        // Data has structure {uint8 firstDex}{uint8 secondDex}{uint80 amount}{bytes20 middlePath}
        assembly {
            let ptr := mload(0x40)  // Pointer no next free memory location
            calldatacopy(ptr, 4, 36)  // load bytes32 input (first 4 bytes are reserved to the function signature)
            firstDex := mload(sub(ptr, 31))
            secondDex := mload(sub(ptr, 30))

            // bytes 3-12 hold 1/16th amount as uint80 (can represent values up to 2**84 wei = 19.3M BNB)
            tmpAmount := mload(sub(ptr, 20))

            // 20 least significant bytes hold the address
            token := mload(ptr)
        }
        amountLast = BNB_DENOMINATOR * tmpAmount;
        (
            address firstPair,
            address secondPair,
            uint256 amountInFirst,
            uint256 amountInSecond
        ) = _get_pairs_amounts_32(firstDex, secondDex, token, amountLast);
        TransferHelper.safeTransfer(WBNB, firstPair, amountInFirst);
        (address token0,) = PancakeswapLibrary.sortTokens(WBNB, token);

        (uint256 amount0Out, uint256 amount1Out) = token0 == WBNB ? (uint(0), amountInSecond) : (amountInSecond, uint(0));
        IUniswapV2Pair(firstPair).swap(amount0Out, amount1Out, secondPair, new bytes(0));

        (amount0Out, amount1Out) = token0 == WBNB ? (amountLast, uint(0)) : (uint(0), amountLast);
        IUniswapV2Pair(secondPair).swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function _get_pairs_amounts_32(
        uint8 firstDex,
        uint8 secondDex,
        address token,
        uint256 amountLast
    ) internal view returns(address firstPair, address secondPair, uint256 amountInFirst, uint256 amountInSecond) {
        {  // scope to avoid stack too deep errors
        (address secondFactory, bytes32 secondHash, uint256 secondFee) =
            secondDex == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        secondPair = PancakeswapLibrary.pairFor(secondFactory, secondHash, WBNB, token);
        (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(secondPair, token, WBNB);
        amountInSecond = PancakeswapLibrary.getAmountIn(amountLast, reserveIn, reserveOut, secondFee);
        }
        (address firstFactory, bytes32 firstHash, uint256 firstFee) =
            firstDex == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        firstPair = PancakeswapLibrary.pairFor(firstFactory, firstHash, WBNB, token);
        (uint256 reserveIn, uint256 reserveOut) = PancakeswapLibrary.getPairReserves(firstPair, WBNB, token);
        amountInFirst = PancakeswapLibrary.getAmountIn(amountInSecond, reserveIn, reserveOut, firstFee);

        require(amountInFirst < amountLast, 'LR');
    }

    // function swap64_F5e(  // 0x000217b7
    //     bytes32,
    //     address path2
    // ) external discountCHIOn restricted {
    //     uint8 firstDex;
    //     uint8 secondDex;
    //     uint256 amountLast;
    //     address[] memory path;
    //     uint80 tmpAmount;
    //     // Data has structure {uint8 firstDex}{uint8 secondDex}{uint80 amount}{bytes20 middlePath}
    //     assembly {
    //         let ptr := add(mload(0x40), 0x20)  // Set pointer to to the location of path[1] (next free memory from 0x40 plus space for path[0])
    //         calldatacopy(ptr, 4, 36)  // load bytes32 input (first 4 bytes are reserved to the function signature)
    //         firstDex := mload(sub(ptr, 31))
    //         secondDex := mload(sub(ptr, 30))

    //         // bytes 3-12 hold 1/16th amount as uint80 (can represent values up to 2**84 wei = 19.3M BNB)
    //         tmpAmount := mload(sub(ptr, 20))

    //         mstore(path, 3)
    //         mstore(add(path, 0x20), WBNB)
    //         mstore(add(path, 0x80), WBNB)
    //     }
    //     path[2] = path2;
    //     amountLast = BNB_DENOMINATOR * tmpAmount;
    //     (
    //         address[] memory pairs,
    //         uint256[] memory amounts
    //     ) = _get_pairs_amounts(firstDex, secondDex, amountLast, path);
    // }

    // function _get_pairs_amounts(
    //     uint8 firstDex,
    //     uint8 secondDex,
    //     uint256 amount,
    //     address[] memory path
    // ) internal view returns (address[] memory pairs, uint256[] memory amounts) {
    //     (address firstFactory, bytes32 firstHash, uint256 firstFee) =
    //         firstDex == PCS_1
    //             ? (pcs1Factory, initCodeHash1, pcs1Fee)
    //             : (pcs2Factory, initCodeHash2, pcs2Fee);
    //     (address secondFactory, bytes32 secondHash, uint256 secondFee) =
    //         secondDex == PCS_1
    //             ? (pcs1Factory, initCodeHash1, pcs1Fee)
    //             : (pcs2Factory, initCodeHash2, pcs2Fee);
    //     pairs = new address[](path.length + 1);
    //     pa = PancakeswapLibrary.pairFor(firstFactory, firstHash, WBNB, path[0]);
    //     secondPair = PancakeswapLibrary.pairFor(secondFactory, secondHash, WBNB, token);
    // }

    function flash_oHM(  // 0x00009d17
        bytes calldata data,
        uint256 amount
    ) external discountCHIOn restricted {
        (uint8 firstDex,, address[] memory path) = AddressArrayEncoder.decodeWithHeader2(data);
        address pcs1Pair;
        address token0;
        {  // Scope to avoid stack too deep error
        (address firstFactory, bytes32 firstHash) = firstDex == PCS_1 ? (pcs1Factory, initCodeHash1) : (pcs2Factory, initCodeHash2);
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
        (uint8 firstDex, uint8 secondDex, address[] memory path) = AddressArrayEncoder.decodeWithHeader2(data);
        uint256 amountSendPair = amount0 == 0 ? amount1 : amount0;

        (address firstFactory, bytes32 firstHash, uint256 firstFee) =
            firstDex == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);
        (address secondFactory, bytes32 secondHash, uint256 secondFee) =
            secondDex == PCS_1
                ? (pcs1Factory, initCodeHash1, pcs1Fee)
                : (pcs2Factory, initCodeHash2, pcs2Fee);

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
}
