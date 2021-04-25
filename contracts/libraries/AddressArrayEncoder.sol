// SPDX-License-Identifier: GPL-3.0-only
pragma solidity >=0.6.0;


library AddressArrayEncoder{
    function bytesToAddress(bytes calldata data) internal pure returns (address addr) {
        bytes memory b = data;
        assembly {
          addr := mload(add(b, 20))
        }
    }

    function bytesToHeader(bytes calldata data) internal pure returns (uint8 header) {
        bytes memory b = data;
        assembly {
          header := mload(add(b, 8))
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

    function decodeWithHeader(bytes calldata data) internal pure returns(uint8 header, address[] memory addresses) {
        uint n = data.length / 20;
        addresses = new address[](n);

        header = bytesToHeader(data);

        for(uint i = 0; i < n; i++){
            addresses[i] = bytesToAddress(data[i * 20 + 8:(i + 1) * 20 + 8]);
        }
    }

    function encodeWithHeader(uint8 header, address[] calldata addresses) internal pure returns(bytes memory data) {
        data = abi.encodePacked(header);
        for(uint i = 0; i < addresses.length; i++){
            data = abi.encodePacked(data, addresses[i]);
        }
    }
}
