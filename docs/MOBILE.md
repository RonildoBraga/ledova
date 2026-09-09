# Mobile builds and security

The mobile app uses the versions resolved by `mobile/package-lock.json`: Expo
54.0.33, React Native 0.81.5, React 19.1.0, SecureStore 15.0.8 and Expo Crypto
15.0.8. Native projects are generated from `app.json` and the local config plugin;
`android/` and `ios/` are not committed. Use a native development build to test
these policies. Expo Go does not contain Ledova's native networking overrides.

## Transport

Release builds require HTTPS for API requests, trading SSE and provider WebViews.
The shared URL policy refuses credentials embedded in URLs, fragments, malformed
URLs and any bearer destination outside `EXPO_PUBLIC_API_URL`'s origin. Axios
absolute URLs and `baseURL` overrides pass through the same check. An absent
stored session removes an existing Authorization header before dispatch.

Native Debug allows exact `localhost`, `127.0.0.1`, `::1` and `10.0.2.2` hosts.
For a physical development device, set `EXPO_PUBLIC_DEV_API_HOST` to one private
LAN IPv4 and set the API/marketing URLs to that host before prebuild. Ports are
not restricted by the native allowlist. Do not put credentials in `EXPO_PUBLIC_`
variables; Expo embeds them in the bundle. Changing the native allowance requires
regeneration and rebuilding. A Release build made from a Debug-configured
prebuild still denies cleartext.

Android uses separate main/Debug network security resources. iOS uses separate
Release/Debug plists and a compile-time HTTP guard in its request handler, including
numeric IP addresses. This matters on supported older Apple systems where ATS
alone does not cover every local/numeric destination. [Android network security
configuration](https://developer.android.com/privacy-and-security/security-config)
and [Apple's ATS reference](https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/CocoaKeys.html)
describe the platform behavior.

The API must serve requests directly. Android's existing RN OkHttp client and an
iOS subclass of RN's existing HTTP handler refuse redirects, including 307/308
requests that could otherwise forward sign-in or refresh bodies. The iOS handler
is registered through RN's new-architecture protocol provider. Normal platform
TLS validation, request cancellation, progress, multipart uploads and SSE remain
in the inherited networking implementation. Provider WebViews keep their own
navigation behavior and capabilities; they reject insecure initial URLs,
insecure navigation and mixed content.

## Secret storage

Ordinary access/refresh tokens share a fresh `session.tokens.v2` SecureStore item
with `WHEN_UNLOCKED_THIS_DEVICE_ONLY`, without requiring biometric authentication.
A healthy complete legacy pair migrates only after replacement read-back and
verified removal of both originals. Incomplete or failed migration exposes no
credentials. A serial queue orders session and biometric mutations. Refresh
responses can update or retire only the generation and refresh identity captured
before their request, so late responses cannot recreate a logged-out session or
replace a newer sign-in.

Logout persists a non-secret retirement marker, removes the ordinary pair and
verifies its absence without an authentication prompt. If native deletion silently
leaves the pair behind, reads remain refused after an app restart and logout
reports failure. An unavailable retirement-marker write refuses reads in the
running process; durable retirement cannot be guaranteed while the storage
provider itself cannot write. A deliberate successful sign-in activates a new
pair. Optional biometric sign-in stays optional: its ready marker is retired and
verified without prompting. Expo's iOS native deletion ignores Keychain deletion
status, so physical erasure of the separately gated copy is not verified by
prompt-free logout; the app refuses reads through its retired marker.

Wallet seeds use a fresh gated key and service with
`WHEN_PASSCODE_SET_THIS_DEVICE_ONLY` and `requireAuthentication`. Reads do not
trust the old secured marker. A legacy migration authenticates, writes and reads
back the new gated item, then verifies removal of the original before returning
the phrase. Failure returns no phrase and preserves whichever recoverable copy
already exists. This avoids Expo's iOS preference for a surviving no-auth alias
at the old key. Cancellation, unavailable protection and failed storage do not
fall back to ungated seed access.

Android retains SecureStore's exclusions in both legacy backup XML and Android
12+ cloud/device-transfer rules. Existing non-secret preference backups remain
enabled. iOS device-only accessibility prevents transfer of the selected secret
items to another device; it does not disable backups of the entire app container.
SecureStore can persist across iOS uninstall/reinstall, and biometric enrollment
or passcode changes can invalidate gated items. Keep a recovery phrase outside
the app under the existing wallet recovery procedure. These platform semantics
are documented by [Expo SecureStore](https://docs.expo.dev/versions/v54.0.0/sdk/securestore/)
and [Android backup rules](https://developer.android.com/identity/data/autobackup).

## Native dependencies and randomness

The RNG entry shim and mnemonic generation use Expo Crypto's native
`getRandomValues` directly and throw when it is unavailable. The removed
`react-native-get-random-values` dependency had a remote-debugging `Math.random`
fallback. Temporary mnemonic entropy is overwritten after conversion; that is
not a claim that JavaScript strings or all native copies can be securely erased.
The remaining Buffer, process, crypto-browserify, stream, events, assert and util
shims support the existing wallet/Keystone dependency graph. Resolution checks,
BIP39/BIP44 derivation/signature vectors and the native probe cover their use.

The lockfile keeps registry URLs and npm integrity values; the shared workspace
is the intentional local link. Install with `--ignore-scripts` in native CI.
The locked packages declaring install scripts are watcher, fsevents,
unrs-resolver and secp256k1; secp256k1 enters through Keystone's hdkey dependency.
No broad dependency upgrade or full transitive source audit is implied.

Each native run records the resolved Android release dependency graph and
repository configuration, or the resolved Podfile.lock and generated iOS protocol
provider in CI. The generated Android repositories are Google Maven, Maven
Central and JitPack. The Gradle 8.14.3 distribution is SHA-256 pinned by the
plugin. Native dependency graphs still need review when they change; npm's
lockfile does not itself pin every downloaded Maven/Pod artifact. The ordinary
APK is checked for both ZIP alignment and every native library's ELF load-segment
alignment at 16 KiB. [RN 0.81's compatibility statement](https://reactnative.dev/blog/2025/08/12/react-native-0.81)
does not replace checking third-party binaries.

RN 0.81.5 can turn an empty app spec search into a codegen dependency on the
entire iOS project directory, creating a cycle with Expo's generated provider.
The plugin's CocoaPods post-install helper removes only the exact
`${PODS_ROOT}/..` input from ReactCodegen's Generate Specs phase. Real spec inputs,
generation commands and handler registration remain intact. iOS CI checks this
with a genuine native spec control and preserves the generated Podspec and Pods
project for build diagnosis.

## Local build and probe

| Component | Build baseline |
| --- | --- |
| Node / npm | 22.15.1 / 11.5.2 |
| Android | JDK 17, SDK/target 36, minimum API 24, Build Tools 36.0.0 |
| Android native toolchain | NDK 27.1.12297006, CMake 3.22.1, Gradle 8.14.3, Kotlin 2.1.20 |
| iOS | Xcode 16.4, minimum deployment target 15.1, unsigned simulator Release |
| Runtime probes | Android API 36 x86_64 emulator; iOS 18.5 simulator |

These minimum platform versions follow [Expo SDK 54](https://docs.expo.dev/versions/v54.0.0/).
The Android build includes ARM64 and x86_64; only the emulator architecture is
executed here. Some native subprojects also request Android Build Tools 35.0.0,
which Gradle installs when its SDK license is available. Current Android command
line tools may require JDK 21 for SDK installation; select JDK 17 for Gradle.

Install the SDK/NDK/CMake packages from the table, plus platform-tools, emulator
and `system-images;android-36;google_apis;x86_64`. Put SDK, Gradle cache and AVDs
in owned directories when sharing a machine; do not reuse a personal device or
live development service. On macOS, install CocoaPods and the iOS 18.5 simulator
runtime. The exact CI setup is in
[mobile-native.yml](../.github/workflows/mobile-native.yml), which selects
[Xcode 16.4 on the macOS 15 runner](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-Readme.md).
No EAS account or signing credentials are needed.

From a clean checkout:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm --prefix mobile ci --ignore-scripts --no-audit --no-fund
cd mobile
EXPO_PUBLIC_DEV_API_HOST=192.168.50.10 npm run native:prebuild
EXPO_PUBLIC_DEV_API_HOST=192.168.50.10 npm run check:native
```

Prebuild replaces generated projects; preserve any local native experiments
first. For iOS, also run `cd ios && pod install` before returning to `mobile/`.
Boot a dedicated emulator/simulator, then select it explicitly:

```bash
ANDROID_SERIAL=emulator-5556 npm run test:native -- android /absolute/fresh/android-results
IOS_SIMULATOR_UDID=your-owned-simulator-uuid npm run test:native -- ios /absolute/fresh/ios-results
```

The output directory must not already exist. The runner builds and launches the
ordinary Release app, preserves that artifact and checks its release policy. It
gives each build phase its own temporary/cache directory so Expo's CI cache
cannot retain a previous phase's API destination. The probe checks the compiled
API client and policy destinations against its isolated server.
Server startup has a 120-second deadline and each certificate tool call has a
30-second timeout. Certificate generation uses its own OpenSSL configuration and
explicit CA/leaf extensions, avoiding duplicate extensions from older tools'
ambient defaults. Before building, strict host requests check both CA-signed
endpoints, an independently trusted leaf and wrong-CA refusals. Top-level evidence
includes the selected tool path/version, configuration hash and public certificate
diagnostics; private keys are not uploaded. Named stages, including each probe
reset, and separate primary/cleanup errors identify
infrastructure failures without recording request credentials or bodies. Xcode
commands have a 45-minute deadline; other asynchronous commands retain their
30-minute limit, and the iOS CI job remains bounded to 90 minutes. A timeout
terminates the owned command group and is reported separately from an exit code
or signal. The runner
then builds a separate test entry against loopback TLS servers with a generated
CA. Android receives a temporary test-only trust resource; iOS receives the CA
only in the owned simulator keychain. The ordinary artifact retains its normal
trust. An untrusted certificate with the same hostname/IP coverage must fail.

The runner first enables native redirects in generated source and requires both
307/308 refusal assertions to fail while the target receives exactly two
requests. It restores the policy and requires zero redirected target requests,
with successful direct bearer/body, API refresh, native entropy and signing,
file upload/download, streaming and cancellation controls. Numeric HTTP requests
must fail, including repeated refusal/cancellation. An unenrolled Android
emulator additionally checks gated-wallet refusal while preserving a legacy
recovery copy. SIGINT/SIGTERM cancel the runner, terminate its owned
command/server groups
(with forced termination after a two-second grace period), reap direct children,
and restore generated files. Short synchronous tool calls have timeouts.
An uncatchable kill or host loss requires a fresh prebuild before using the
generated project. Remove only the owned emulator/simulator afterward. Deleting
the iOS simulator also removes its test CA.
Do not distribute the probe artifact.

Jest and native probe outcomes are recorded separately. A simulator does not
establish physical biometric enrollment/change, hardware-backed key properties,
OEM backup/transfer, store distribution or behavior on every supported OS.
Record those limits, any failed native build and the exact tested head in the PR;
JavaScript tests alone do not close a native hardening claim.
