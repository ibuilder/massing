// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721URIStorage} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title MassRelease721
/// @notice One ERC-721 token per sealed `.mass` release, bound immutably to a `content_hash`.
/// @dev The off-chain manifest (IPFS) carries human-readable metadata; `contentHash` is the anchor.
contract MassRelease721 is ERC721URIStorage, Ownable {
    uint256 private _nextTokenId = 1;

    /// @dev contentHash => tokenId. Zero means unminted.
    mapping(bytes32 => uint256) public hashToToken;

    event ReleaseMinted(
        address indexed to,
        uint256 indexed tokenId,
        bytes32 indexed contentHash,
        string assetUrn,
        string tokenURI
    );

    constructor(address initialOwner) ERC721("Massing Release", "MASSREL") Ownable(initialOwner) {}

    /// @notice Mint one token for a release identity. Reverts if `contentHash` was already minted.
    /// @param to Recipient wallet.
    /// @param contentHash SHA-256 digest of the release payload (32 bytes, no prefix).
    /// @param assetUrn Stable lineage URN, e.g. `urn:massing:asset:…` (stored in event only).
    /// @param tokenURI Metadata URI (typically `ipfs://…`).
    function mintRelease(
        address to,
        bytes32 contentHash,
        string calldata assetUrn,
        string calldata tokenURI
    ) external onlyOwner returns (uint256 tokenId) {
        require(contentHash != bytes32(0), "contentHash required");
        require(hashToToken[contentHash] == 0, "already minted");
        require(to != address(0), "recipient required");
        require(bytes(tokenURI).length > 0, "tokenURI required");

        tokenId = _nextTokenId++;
        hashToToken[contentHash] = tokenId;
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, tokenURI);

        emit ReleaseMinted(to, tokenId, contentHash, assetUrn, tokenURI);
    }

    /// @notice Read the on-chain binding for a release hash. Returns 0 if never minted.
    function tokenIdForHash(bytes32 contentHash) external view returns (uint256) {
        return hashToToken[contentHash];
    }
}
