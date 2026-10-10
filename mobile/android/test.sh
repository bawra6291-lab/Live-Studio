#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/tests
javac --release 8 -d build/tests src/org/livedesk/mobile/LanAddress.java tests/LanAddressTest.java src/org/livedesk/mobile/ConnectionAddress.java tests/ConnectionAddressTest.java
java -cp build/tests LanAddressTest
java -cp build/tests ConnectionAddressTest
