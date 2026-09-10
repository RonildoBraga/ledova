# Mobile builds and security

The mobile app uses the versions resolved by `mobile/package-lock.json`: Expo
54.0.33, React Native 0.81.5, React 19.1.0, SecureStore 15.0.8 and Expo Crypto
15.0.8. Native projects are generated from `app.json` and the local config plugin;
`android/` and `ios/` are not committed. Use a native development build to test
these policies. Expo Go does not contain Ledova's native networking overrides or
Android scanner owning-view module.

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

## Create-order recovery

Starting a new buy or sell order saves a fresh submission identity in AsyncStorage
before requesting a signing challenge. Each record contains only the protocol
version and user, account, wallet and submission UUIDs. Terms, challenges,
signatures, seeds and bearer tokens are not saved with it. A read/write or
verification failure prevents the first signing request. Equal terms submitted
as explicit new orders remain separate orders; the saved-orders list retains
multiple unresolved submissions for the current user and account.

Closing the draft or signing window, changing account, or retiring the session
prevents stale seed-read continuations, signing results and authenticated HTTP
replays. An already sent request can still finish on the server. Its saved
identity remains available for authenticated recovery after closing or restarting.
Recovery reads the original terms or recorded outcome before requesting another
challenge. A missing or inaccessible lookup stays unconfirmed; it never supplies
invented terms or silently starts a replacement. Confirmed outcomes show the
order's current state, including later changes or cancellation. A terminal refusal
requires an explicit new order to try again with a new identity.

The shared hooks use the mobile copies of React and React Query in both Metro and
Jest. Metro reanchors only those package imports and subpaths to the mobile
entrypoint, then delegates to Expo's resolver. The earlier dependency-alias check
established availability, not singleton identity when root and mobile dependencies
were both installed. `npm --prefix mobile run check:resolution` now also resolves
those peers from the app and shared hook on iOS and Android and compares their
actual file paths. This filesystem resolver control complements native builds;
it does not exercise a physical biometric prompt or hardware wallet.

## QR scanner permission timing

The shared modal, animated wallet importer and wallet-verification scanner use
one camera permission controller. Hidden scanners do not read or request
permission or mount a preview. Opening a scanner checks the current permission
and makes one request when the platform allows asking again. Concurrent openings
share an outstanding request. Denial and native getter/request failures do not
loop; closing and opening the scanner again permits another attempt.

Leaving the foreground removes the preview and invalidates its callbacks.
Returning refreshes permission, including changes made in settings, without
asking again. A pending native response cannot restore an old preview or override
a newer refresh. Closing, unmounting or leaving the verification scan step also
retires callbacks. Verification pauses while another navigation route covers it.
A completed scan retires its callback before delivering the result, removes its
preview on the next render and stays completed across foreground changes.

The animated importer retains its UR fragments during a permission refresh and
clears them on a new opening. Wallet verification requests permission at the scan
step, after the challenge; software-wallet verification does not use the camera.
An unsupported signature QR displays guidance and leaves scanning available.

The app-lock provider also pauses camera admission during initialization,
backgrounding, a pending foreground lock decision and the locked overlay. Its
synchronous admission snapshot blocks permission work and retained callbacks
before React removes the preview, regardless of provider/scanner listener order.
A newer background transition or an authorized unlock/disable retires an older
lock decision. Unlock refreshes permission without requesting it again; an opening
first made while locked is passive until a later explicit close/reopen. A lock
pause preserves completed scans, accumulated UR parts and the verification
challenge/step. The optional lock setting, existing session criterion, absence
threshold and biometric/passcode fallback remain unchanged.

On Android, each scanner has its own native container in its actual window,
including the scanner modal's window. Admission requires attachment, window
visibility, visible ancestors and that window's focus. Activity focus is not a
proxy: the scanner's own modal legitimately leaves its Activity unfocused.
The container remains mounted while permission is pending or denied. An explicit
opening retains its one request opportunity until its first window admission;
loss and regain caused by that permission dialog only refresh permission.
Events from an earlier owner or revision cannot admit a replacement scanner.

The source-selected Expo Camera patch releases only the retiring view's use
cases, fences delayed camera creation and old ready/barcode callbacks, and
permanently revokes that native camera instance after owning-window loss. A fresh
window revision acknowledged by the current JavaScript scanner mounts a new
instance. Native focus returning before JavaScript handles the loss cannot reopen
the old instance. A completed session stays completed and animated UR progress
survives a window pause. These Android changes do not change iOS admission.

Component tests exercise the installed Expo permission methods at a controlled
native boundary, actual UR encoding/decoding and verification step/mutation
hooks, plus the actual app-lock provider with delayed session/authentication
responses. They establish JavaScript request, callback and mount timing. OS prompt
presentation, physical camera shutdown, device settings/OEM behavior and global
lock-overlay/input stacking are not established by these controls and remain
under #13. Android owning-window and use-case release evidence comes from the
separate native camera probe only when that exact source and artifact run passes.

## Identity-provider WebView lifetime

The signup and profile verification forms mount their provider WebView only
while their owner is visible and focused, the app is active, and the app-lock
provider admits camera use. Initialization, foreground lock evaluation and the
locked overlay remove the WebView. A synchronous admission/session check also
rejects retained completion, navigation and load callbacks before React removes
the native view. Returning from a lock or foreground pause mounts a fresh view
for the same form; a completed or closed form stays retired.

Closing, replacing credentials, leaving the owning screen or retiring the session
invalidates pending form launches and old callbacks. A later explicit launch can
open a new form. Normal successful submission and its existing status polling
continue; hiding the owner alone does not stop submitted-status polling. Provider
SDK failures and native page-load failures use fixed messages instead of raw
provider or WebView error payloads. Existing backend initialization error messages
are still shown.

Mounted JavaScript controls use the locked WebView wrapper, actual app-lock
provider and owner hooks with synthetic credentials. They establish mount,
callback and error-display behavior, not physical camera shutdown or native
permission-dialog cancellation. Provider origin/media grants, Android owning-window
focus and global modal/lock stacking remain separate #13 checks. Navigation and
provider media policies are unchanged; playback settings do not establish camera
capture control, and a form-completion signal is not server verification approval.

## Document upload copies

Eligibility and company listing use one serialized document picker. A returned
file is accepted only when its URI identifies a generated UUID filename directly
inside Expo's private `DocumentPicker` cache. Provider originals and unrelated
cache files are never deletion targets. Unexpected multiple results are refused,
with each recognized private copy retired. Native/provider errors are presented
without their raw diagnostic text.

Before attachment, the actual copied file must be non-empty, at most 10 MiB,
and match the provider's reported size when present. This check happens after
native copying; it cannot bound a cloud-provider download or temporary copy that
has not returned to JavaScript. The copy moves into one of 16 fixed private
`ledova-upload-copies-v1/slot-*` files. The original URI is retained separately
and its retirement verified: Expo's move changes its object's URI, and supported
Android versions below API 26 can report success without deleting the source.

A selected copy and its admitted upload consumers have separate lifetimes.
Replacement, abandonment, screen/account changes and session retirement release
the selection. Bytes remain until every admitted upload promise settles,
including refresh/replay and mutation completion. Eligibility retains a failed
submission for retry; listing has no retained-file retry and releases its copy
after either result. A late picker result or old success cannot replace or reset
a newer draft. Already sent requests may still complete on the server.

These uploads carry the session epoch captured with their selection. Fresh login,
biometric entry from an absent session, and logout invalidate it; ordinary token
rotation preserves it. Credential reads, refresh entry and replay check that
epoch so an old upload cannot acquire a newer login's credentials. Conditional
retirement from an obsolete refresh does not invalidate a newer session.

Before another picker opens, cleanup checks only the 16 exact managed paths,
preserving active selections and consumers. This retires managed copies left by
a previous process on next use without listing the cache directory. Metadata or
deletion failure leaves a slot unavailable for reuse; it is not reported as
verified erasure. Expo copies from before adoption, unreturned partial copies and
older versions remain a separate cleanup gap. Viewer/sharing copies also need a
separate external-reader lifetime and are outside this upload cache.

Component tests control native picker and file boundaries while retaining the
actual upload hooks and React Query mutation lifecycle. The native probe supplies
a synthetic picker result and exercises actual file move, retention, multipart
upload and retirement on the emulator/simulator; it does not drive the system
picker UI. Local/cloud-provider, low-storage and physical-device checks remain
under #13, alongside the pre-adoption and sharing gaps.

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

Android explicitly builds `expo-camera` 17.0.10 from its installed Kotlin source
with `expo.autolinking.android.buildFromSource`. Its default Maven publication
would otherwise ignore an installed-source edit. Android prebuild applies
`mobile/patches/expo-camera-17.0.10.json`; the adjacent unified patch is the
reviewable difference. Both original and resulting Kotlin hashes, package
version, module publication configuration and Gradle dependency declarations
must match. The local `ledova-camera-window` module verifies those inputs on
direct Gradle configuration too. A changed dependency requires reviewing and
updating this exact patch, not bypassing the verifier.

Preparation refuses linked external dependency directories. Use a private
installation or owned copy before prebuild; do not patch another checkout's
`node_modules`. `node scripts/prepare-camera-android.mjs verify` checks the
ordinary source without changing it. The upstream package's license and headers
are retained; no native dependency version is changed by this patch.

RN 0.81.5 can turn an empty app spec search into a codegen dependency on the
entire iOS project directory, creating a cycle with Expo's generated provider.
The plugin's CocoaPods post-install helper removes only the exact
`${PODS_ROOT}/..` input from ReactCodegen's Generate Specs phase. Real spec inputs,
generation commands and handler registration remain intact. iOS CI checks this
with a genuine native spec control and preserves the generated Podspec and Pods
project for build diagnosis.

## Local build and probe

| Component                | Build baseline                                                              |
| ------------------------ | --------------------------------------------------------------------------- |
| Node / npm               | 22.15.1 / 11.5.2                                                            |
| Android                  | JDK 17, SDK/target 36, minimum API 24, Build Tools 36.0.0                   |
| Android native toolchain | NDK 27.1.12297006, CMake 3.22.1, Gradle 8.14.3, Kotlin 2.1.20               |
| iOS                      | Xcode 16.4, minimum deployment target 15.1, ad hoc signed simulator Release |
| Runtime probes           | Android API 36 x86_64 emulator; iOS 18.5 simulator                          |

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

Pull requests whose complete changes are confined to `backend/` and `docs/`
skip the two native builds. Ordinary CI still runs, including gates that read
documentation. Native/configuration/package inputs and unknown paths run both
platforms; an unavailable comparison, a base ahead of the branch, or an empty
comparison also runs both. Main pushes and manual runs remain unconditional to
check external tool and dependency drift. The always-run `Mobile native checks`
verdict requires successful classification and the expected platform results.
Require that verdict when configuring branch protection. A new native input
from an excluded directory must update this boundary when it is introduced.

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
ordinary Release app, preserves that artifact and checks its release policy.
iOS uses Xcode's normal ad hoc simulator signing without an Apple account or
signing certificate. Before each ordinary/probe installation, it checks both built
architectures' `__TEXT,__entitlements` sections for the app identity and preserves
their public entitlements. Simulator entitlements are distinct from the code
signature's entitlements; disabling signing can omit the former and break Keychain
controls despite successful compilation and launch. Existing app capabilities
remain in the generated entitlements. Each build phase gets its own
temporary/cache directory so Expo's CI cache cannot retain a previous phase's API
destination. The probe checks the compiled
API client and policy destinations against its isolated server.
Server startup has a 120-second deadline. Each certificate or simulator inspection
tool call has a 30-second timeout. Certificate generation uses its own OpenSSL
configuration and explicit CA/leaf extensions, avoiding duplicate extensions from older tools'
ambient defaults. Before building, strict host requests check both CA-signed
endpoints, an independently trusted leaf and wrong-CA refusals. Top-level evidence
includes the selected tool path/version, configuration hash and public certificate
diagnostics; private keys are not uploaded. Named stages, including each probe
reset, and separate primary/cleanup errors identify
infrastructure failures without recording request credentials or bodies. Native
probe failures also carry a fixed error category and operation stage, never raw
error messages, stacks or values. Categories do not establish a Keychain OSStatus.
Xcode commands have a 45-minute deadline; other asynchronous commands retain their
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

Android then builds three additional camera-only probe APKs. The probe installer
accepts only the exact upstream, review-red or corrected camera bodies plus the checked-in
instrumentation and `native-tests/camera-window.tsx` entrypoint. Ordinary builds
refuse these test hooks. Each camera probe is saved separately with its digest,
source hashes, compiled class hashes, state observations and screenshot. The
ordinary artifact also receives DEX descriptor/guard-marker checks; those markers
alone are not proof of native behavior. The resolved Gradle graph must select
`:expo-camera`, and the generated module list must contain the local owner module.

The camera probe grants permission to the owned emulator and opens the actual
modal preview. It requires bound use cases and an `OPEN` camera as its positive
control, then actual unbound use cases and `CLOSED` state on window/ancestor loss.
The sustained window cover also tracks the actual bound camera's Camera2 ID:
its probe-owned availability callback must observe unavailable while open, then
available after release. Initial availability cannot satisfy that transition.
Replacement controls permit that physical camera to remain unavailable while the
replacement is open. Emulator availability does not establish physical/OEM behavior.
It injects a fixed synthetic barcode through the compiled camera callback to
check delivery and retirement; it does not prove optical QR recognition. A gate
after the real `awaitInstance` holds camera creation. A first-create live control
is separate from already-open ratio changes, whose real property update enters
the module-scope body before loss, close, detach, pause or owner replacement.
This avoids attributing a view-scope cancellation to the post-await guard.
An additional same-view control holds a 4:3 recreation, lets a later 16:9
recreation bind, then checks that releasing the old continuation preserves the
actual bound capture/analyzer and recorder field identities. A separate control
reads the actual LiveData observer registry before/after production registration
and after rebind/teardown: only the view's observer may disappear, while the
probe's own observer and Activity-bound sibling continue receiving camera state.
These test-only registry reads fail if the loaded implementation cannot expose
those identities; observer counts alone do not establish removal.
Quick native focus cycles run while JavaScript delivery is held, including a
session already completed in JavaScript; an old owner's later cleanup must also
preserve the replacement's `OPEN` camera. The 15 controls preserve the original
13 and add the two recreation/observer checks. The upstream-red expectation is
11 failures; review-red is the exact `8c1088c2` camera body and must fail only the
two added checks; corrected green must pass all 15. These are expectations until
the native runs execute. Sustained-cover release can also occur through JS
cleanup in the old body; that control's expected old-body failure is retired
barcode delivery, not proof of synchronous native release. The extra review-red
build and three dependency-graph checks add native validation time; existing
command/report timeouts remain unchanged.
The runner restores ordinary camera source in `finally`; after an uncatchable
kill, use a fresh owned dependency copy and prebuild before any ordinary build.

Jest and native probe outcomes are recorded separately. A simulator does not
establish physical biometric enrollment/change, hardware-backed key properties,
OEM backup/transfer, store distribution or behavior on every supported OS.
Record those limits, any failed native build and the exact tested head in the PR;
JavaScript tests alone do not close a native hardening claim.
