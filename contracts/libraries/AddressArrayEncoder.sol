// SPDX-License-Identifier: GPL-3.0-only
pragma solidity >=0.6.0;


library AddressArrayEncoder{
    function encode(address[] calldata addresses) internal pure returns(bytes memory data) {
        data = new bytes(0);
        for(uint i; i < addresses.length; i++){
            data = abi.encodePacked(data, addresses[i]);
        }
    }

    function decode(bytes calldata data) internal pure returns(address[] memory addresses) {
        bytes memory data_ = data;
        assembly {
            let n := div(mload(data_), 20)  // n = data.length / 20
            mstore(addresses, n)  // addresses = new addresses[](n)
            for { let i := 0 } lt(i, n) { i := add(i, 1) } {  // for (uint i = 0; i < n; i++)
                mstore(add(addresses, add(32, mul(i, 32))), mload(add(data_, add(20, mul(i, 20)))))  // addresses[i] = data[i * 20:(i + 1) * 20]
            }
        }
    }

    function encodeWithHeader(uint8 header, address[] calldata addresses) internal pure returns(bytes memory data) {
        data = abi.encodePacked(header);
        for(uint i; i < addresses.length; i++){
            data = abi.encodePacked(data, addresses[i]);
        }
    }

    function decodeWithHeader(bytes calldata data) internal pure returns(uint8 header, address[] memory addresses) {
        bytes memory data_ = data;
        assembly {
            header := mload(add(data_, 1))
            let n := div(mload(data_), 20)  // n = data.length / 20
            mstore(addresses, n)  // addresses = new addresses[](n)
            for { let i := 0 } lt(i, n) { i := add(i, 1) } {  // for (uint i = 0; i < n; i++)
                mstore(add(addresses, add(32, mul(i, 32))), mload(add(data_, add(21, mul(i, 20)))))  // addresses[i] = data[i * 20 + 1:(i + 1) * 20 + 1]
            }
        }
    }

    function encodeWithHeader2(uint8 header0, uint8 header1, address[] calldata addresses) internal pure returns(bytes memory data) {
        data = abi.encodePacked(header0, header1);
        for(uint i; i < addresses.length; i++){
            data = abi.encodePacked(data, addresses[i]);
        }
    }

    function decodeWithHeader2(bytes calldata data) internal pure returns(uint8 header0, uint8 header1, address[] memory addresses) {
        bytes memory data_ = data;
        assembly {
            header0 := mload(add(data_, 1))
            header1 := mload(add(data_, 2))
            let n := div(mload(data_), 20)  // n = data.length / 20
            mstore(addresses, n)  // addresses = new addresses[](n)
            for { let i := 0 } lt(i, n) { i := add(i, 1) } {  // for (uint i = 0; i < n; i++)
                mstore(add(addresses, add(32, mul(i, 32))), mload(add(data_, add(22, mul(i, 20)))))  // addresses[i] = data[i * 20 + 2:(i + 1) * 20 + 2]
            }
        }
    }
}
