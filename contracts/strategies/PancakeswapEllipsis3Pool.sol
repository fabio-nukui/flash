// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../interfaces/common/IERC20.sol";
import "../interfaces/curve/ICurveFiPool.sol";
import {PancakeswapLibrary} from "../libraries/uniswap_v2/PancakeswapLibrary.sol";
import "../interfaces/uniswap_v2/IPancakeCallee.sol";


contract PancakeswapEllipsis3Pool is IPancakeCallee, Withdrawable {
    address immutable cake_factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;

    address immutable eps_3pool = 0x160CAed03795365F3A589f10C379FfA7d75d4E76;
    address constant BUSD = 0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56;
    address constant USDC = 0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d;
    address constant USDT = 0x55d398326f99059fF775485246999027B3197955;

    mapping(address => int128) public eps_pool_idx;

    constructor() public {
        eps_pool_idx[BUSD] = 0;
        eps_pool_idx[USDC] = 1;
        eps_pool_idx[USDT] = 2;
    }

    function triggerFlashSwap(
        address token0,
        address token1,
        uint256 amount1
    ) external restricted {
        address cake_pair = PancakeswapLibrary.pairFor(cake_factory, token0, token1);
        (address tokenA, ) = PancakeswapLibrary.sortTokens(token0, token1);
        uint256 amountAOut = tokenA == token1 ? amount1 : 0;
        uint256 amountBOut = tokenA == token1 ? 0 : amount1;

        IUniswapV2Pair(cake_pair).swap(
            amountAOut,
            amountBOut,
            address(this),
            new bytes(1)
        );
        TransferHelper.safeTransfer(token0, owner, IERC20(token0).balanceOf(address(this)));
    }

    function exchangeCurve(
        address fromToken,
        address toToken,
        uint256 amount,
        uint256 minOut
    ) private {
        ICurveFiPool curve = ICurveFiPool(eps_3pool);
        curve.exchange(eps_pool_idx[fromToken], eps_pool_idx[toToken], amount, minOut);
    }

    function pancakeCall(
        address sender,
        uint256 amount0,
        uint256 amount1,
        bytes calldata data
    ) external override {
        address[] memory path = new address[](2);
        uint256 amountSendCurve;
        uint256 amountRepay;
        { // scope for token{0,1}, avoids stack too deep errors
        address token0 = IUniswapV2Pair(msg.sender).token0();
        address token1 = IUniswapV2Pair(msg.sender).token1();
        require(msg.sender == PancakeswapLibrary.pairFor(cake_factory, token0, token1)); // ensure that msg.sender is actually a V2 pair
        require(amount0 == 0 || amount1 == 0); // this strategy is unidirectional
        path[0] = amount0 == 0 ? token0 : token1;
        path[1] = amount0 == 0 ? token1 : token0;
        amountSendCurve = amount0 == 0 ? amount1 : amount0;
        amountRepay = PancakeswapLibrary.getAmountsIn(cake_factory, amountSendCurve, path)[0];
        }
        TransferHelper.safeApprove(path[1], eps_3pool, amountSendCurve);
        exchangeCurve(path[1], path[0], amountSendCurve, amountRepay);
        TransferHelper.safeTransfer(path[0], msg.sender, amountRepay);
    }
}
