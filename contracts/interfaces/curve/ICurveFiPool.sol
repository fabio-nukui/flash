// SPDX-License-Identifier: MIT
pragma solidity ^0.8.3;

abstract contract ICurveFiCurve {
    function get_virtual_price() virtual external returns (uint256 out);

    function add_liquidity(uint256[2] calldata amounts, uint256 deadline) virtual external;

    function get_dy(int128 i, int128 j, uint256 dx) virtual external returns (uint256 out);

    function get_dy_underlying(int128 i, int128 j, uint256 dx)
        virtual
        external
        returns (uint256 out);

    function exchange(
        int128 i,
        int128 j,
        uint256 dx,
        uint256 min_dy
    ) virtual external;

    function exchange(
        int128 i,
        int128 j,
        uint256 dx,
        uint256 min_dy,
        uint256 deadline
    ) virtual external;

    function exchange_underlying(
        int128 i,
        int128 j,
        uint256 dx,
        uint256 min_dy
    ) virtual external;

    function exchange_underlying(
        int128 i,
        int128 j,
        uint256 dx,
        uint256 min_dy,
        uint256 deadline
    ) virtual external;

    function remove_liquidity(
        uint256 _amount,
        uint256 deadline,
        uint256[2] calldata min_amounts
    ) virtual external;

    function remove_liquidity_imbalance(uint256[2] calldata amounts, uint256 deadline)
        virtual external;

    function commit_new_parameters(
        int128 amplification,
        int128 new_fee,
        int128 new_admin_fee
    ) virtual external;

    function apply_new_parameters() virtual external;

    function revert_new_parameters() virtual external;

    function commit_transfer_ownership(address _owner) virtual external;

    function apply_transfer_ownership() virtual external;

    function revert_transfer_ownership() virtual external;

    function withdraw_admin_fees() virtual external;

    function coins(int128 arg0) virtual external returns (address out);

    function underlying_coins(int128 arg0) virtual external returns (address out);

    function balances(int128 arg0) virtual external returns (uint256 out);

    function A() virtual external returns (int128 out);

    function fee() virtual external returns (int128 out);

    function admin_fee() virtual external returns (int128 out);

    function owner() virtual external returns (address out);

    function admin_actions_deadline() virtual external returns (uint256 out);

    function transfer_ownership_deadline() virtual external returns (uint256 out);

    function future_A() virtual external returns (int128 out);

    function future_fee() virtual external returns (int128 out);

    function future_admin_fee() virtual external returns (int128 out);

    function future_owner() virtual external returns (address out);
}
