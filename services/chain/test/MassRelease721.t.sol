// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {MassRelease721} from "../src/MassRelease721.sol";

contract MassRelease721Test is Test {
    MassRelease721 internal nft;
    address internal owner = address(0xA11CE);
    address internal recipient = address(0xBEEF);

    bytes32 internal constant HASH_A =
        0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;
    bytes32 internal constant HASH_B =
        0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;

    function setUp() public {
        vm.prank(owner);
        nft = new MassRelease721(owner);
    }

    function test_mintRelease_bindsHash() public {
        vm.prank(owner);
        uint256 id = nft.mintRelease(recipient, HASH_A, "urn:massing:asset:abc", "ipfs://meta-a");
        assertEq(id, 1);
        assertEq(nft.hashToToken(HASH_A), 1);
        assertEq(nft.ownerOf(1), recipient);
        assertEq(nft.tokenURI(1), "ipfs://meta-a");
    }

    function test_mintRelease_revertsOnDoubleMint() public {
        vm.startPrank(owner);
        nft.mintRelease(recipient, HASH_A, "urn:massing:asset:abc", "ipfs://meta-a");
        vm.expectRevert("already minted");
        nft.mintRelease(recipient, HASH_A, "urn:massing:asset:abc", "ipfs://meta-b");
        vm.stopPrank();
    }

    function test_mintRelease_revertsForNonOwner() public {
        vm.prank(recipient);
        vm.expectRevert();
        nft.mintRelease(recipient, HASH_A, "urn:massing:asset:abc", "ipfs://meta-a");
    }

    function test_tokenIdForHash_unmintedIsZero() public view {
        assertEq(nft.tokenIdForHash(HASH_B), 0);
    }

    function testFuzz_distinctHashesGetDistinctTokens(bytes32 h1, bytes32 h2) public {
        vm.assume(h1 != bytes32(0) && h2 != bytes32(0) && h1 != h2);
        vm.startPrank(owner);
        uint256 id1 = nft.mintRelease(recipient, h1, "urn:massing:asset:1", "ipfs://1");
        uint256 id2 = nft.mintRelease(recipient, h2, "urn:massing:asset:2", "ipfs://2");
        vm.stopPrank();
        assertTrue(id2 > id1);
        assertEq(nft.hashToToken(h1), id1);
        assertEq(nft.hashToToken(h2), id2);
    }
}
