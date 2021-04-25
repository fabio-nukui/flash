// SPDX-License-Identifier: UNLICENCED
pragma solidity ^0.6.6;

import '@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol';

import "../libraries/TransferHelper.sol";
import "../libraries/Withdrawable.sol";
import "../interfaces/common/IERC20.sol";
import "../interfaces/curve/ICurveFiPool.sol";
import "../libraries/uniswap_v2/PancakeswapLibrary.sol";
import "../interfaces/uniswap_v2/IPancakeCallee.sol";
import "../libraries/AddressArrayEncoder.sol";


contract PancakeswapEllipsis3PoolV2 is IPancakeCallee, Withdrawable {
    address immutable cake_factory = 0xBCfCcbde45cE874adCB698cC183deBcF17952812;
    bytes32 constant cakeInitCodeHash = hex'd0d4c4cd0848c93cb4fd1f498d7013ee6bfb25783ea21593d5834f5d250ece66';
    uint32 constant pcsFee = 20;

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
        address[] calldata path,
        uint256 amountLast
    ) external restricted {
        address lastCakePair = PancakeswapLibrary.pairFor(cake_factory, cakeInitCodeHash, path[path.length - 1], path[path.length - 2]);
        (address tokenA, ) = PancakeswapLibrary.sortTokens(path[path.length - 1], path[path.length - 2]);
        uint256 amountAOut = tokenA == path[path.length - 1] ? amountLast : 0;
        uint256 amountBOut = tokenA == path[path.length - 1] ? 0 : amountLast;

        IUniswapV2Pair(lastCakePair).swap(
            amountAOut,
            amountBOut,
            address(this),
            AddressArrayEncoder.encode(path)
        );
        TransferHelper.safeTransfer(path[0], owner, IERC20(path[0]).balanceOf(address(this)));
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
        address[] memory path = AddressArrayEncoder.decode(data);
        uint256 amountSendCurve = amount0 == 0 ? amount1 : amount0;
        uint256[] memory amounts;
        { // scope for token{0,1}, avoids stack too deep errors
        address token0 = IUniswapV2Pair(msg.sender).token0();
        address token1 = IUniswapV2Pair(msg.sender).token1();
        require(msg.sender == PancakeswapLibrary.pairFor(cake_factory, cakeInitCodeHash, token0, token1)); // ensure that msg.sender is actually a V2 pair
        require(amount0 == 0 || amount1 == 0); // this strategy is unidirectional
        amounts = PancakeswapLibrary.getAmountsIn(cake_factory, cakeInitCodeHash, amountSendCurve, path, pcsFee);
        }
        TransferHelper.safeApprove(path[path.length - 1], eps_3pool, amountSendCurve);
        exchangeCurve(path[path.length - 1], path[0], amountSendCurve, amounts[0]);

        address firstPair = PancakeswapLibrary.pairFor(cake_factory, cakeInitCodeHash, path[0], path[1]);
        TransferHelper.safeTransfer(path[0], firstPair, amounts[0]);
        _swap(amounts, path);
    }

    function _swap(uint[] memory amounts, address[] memory path) internal virtual {
        for (uint i; i < path.length - 2; i++) {
            (address input, address output) = (path[i], path[i + 1]);
            (address token0,) = PancakeswapLibrary.sortTokens(input, output);
            uint amountOut = amounts[i + 1];
            (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
            address to = PancakeswapLibrary.pairFor(cake_factory, cakeInitCodeHash, output, path[i + 2]);
            IUniswapV2Pair(PancakeswapLibrary.pairFor(cake_factory, cakeInitCodeHash, input, output)).swap(
                amount0Out, amount1Out, to, new bytes(0)
            );
        }
    }
}
