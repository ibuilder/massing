// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {MassRelease721} from "../src/MassRelease721.sol";

contract DeployMassRelease721 is Script {
    function run() external {
        address owner = vm.envAddress("MASS_RELEASE721_OWNER");
        vm.startBroadcast();
        new MassRelease721(owner);
        vm.stopBroadcast();
    }
}
