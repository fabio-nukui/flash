// SPDX-License-Identifier: GPL-3.0-only
pragma solidity >=0.6.0;


library AddressArrayEncoder{
    function bytesToAddress(bytes calldata data) internal pure returns (address addr) {
        bytes memory b = data;
        assembly {
          addr := mload(add(b, 20))
        }
    }

    function decode(bytes calldata data) internal pure returns(address[] memory addresses) {
        uint n = data.length / 20;
        addresses = new address[](n);

        for(uint i = 0; i < n; i++){
            addresses[i] = bytesToAddress(data[i * 20 + 1:(i + 1) * 20 + 1]);
        }
    }

    function encode(address[] calldata addresses) internal pure returns(bytes memory data) {
        data = new bytes(1);
        for(uint i = 0; i < addresses.length; i++){
            data = abi.encodePacked(data, addresses[i]);
        }
    }
}
