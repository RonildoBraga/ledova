import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

export const probeSupportPath = 'android/src/main/java/expo/modules/camera/LedovaCameraWindowProbe.kt';
export const probeEntry = 'native-tests/camera-window.tsx';

let transformations;

function once(source, before, after) {
  if (transformations) transformations.push({ before, after });
  assert.equal(source.split(before).length - 1, 1, 'Camera probe must instrument the actual expected body.');
  return source.replace(before, after);
}

export function instrumentCamera(file, source) {
  if (file.endsWith('/ExpoCameraView.kt')) {
    source = once(
      source,
      '    val cameraProvider = ProcessCameraProvider.awaitInstance(context)',
      '    val cameraProvider = ProcessCameraProvider.awaitInstance(context)\n    LedovaCameraWindowProbe.afterProvider(this, cameraProvider)',
    );
    source = once(
      source,
      '      camera = cameraProvider.bindToLifecycle(currentActivity, cameraSelector, useCases)',
      '      LedovaCameraWindowProbe.attempt(this)\n      camera = cameraProvider.bindToLifecycle(currentActivity, cameraSelector, useCases)\n      LedovaCameraWindowProbe.bound(this, cameraProvider, camera!!, listOfNotNull<androidx.camera.core.UseCase>(preview, if (cameraMode == CameraMode.PICTURE) imageCaptureUseCase else videoCapture, if (cameraMode == CameraMode.PICTURE) imageAnalysisUseCase else null), currentActivity)',
    );
    source = once(
      source,
      '        observeCameraState(it.cameraInfo)',
      '        LedovaCameraWindowProbe.beforeObserve(this, it.cameraInfo)\n        observeCameraState(it.cameraInfo)\n        LedovaCameraWindowProbe.afterObserve(this, it.cameraInfo)',
    );
    source = once(
      source,
      '          onCameraReady(Unit)',
      '          LedovaCameraWindowProbe.ready(this)\n          onCameraReady(Unit)',
    );
    return once(
      source,
      '      onBarcodeScanned(\n        BarcodeScannedEvent(',
      '      LedovaCameraWindowProbe.barcode(this)\n      onBarcodeScanned(\n        BarcodeScannedEvent(',
    );
  }
  return once(
    source,
    '    Events("onModernBarcodeScanned")',
    `    Events("onModernBarcodeScanned")
    AsyncFunction("cameraProbeSnapshot") { LedovaCameraWindowProbe.snapshot(appContext.throwingActivity) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeArm") { LedovaCameraWindowProbe.arm() }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeRelease") { id: Int -> LedovaCameraWindowProbe.release(id) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeRetire") { id: Int -> LedovaCameraWindowProbe.retire(id) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbePause") { id: Int -> LedovaCameraWindowProbe.pause(id) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeScan") { id: Int -> LedovaCameraWindowProbe.scan(id) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeDetach") { id: Int -> LedovaCameraWindowProbe.detach(id) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeReattach") { id: Int -> LedovaCameraWindowProbe.reattach(id) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeVisibility") { id: Int, visible: Boolean -> LedovaCameraWindowProbe.visibility(id, visible) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeCover") { LedovaCameraWindowProbe.showCover(appContext.throwingActivity) }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeUncover") { LedovaCameraWindowProbe.hideCover() }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeReset") { LedovaCameraWindowProbe.reset() }.runOnQueue(Queues.MAIN)
    AsyncFunction("cameraProbeCycle").SuspendBody { id: Int -> LedovaCameraWindowProbe.cycleFocus(appContext.throwingActivity, id) }.runOnQueue(Queues.MAIN)`,
  );
}

export function probeSupport(root) {
  return fs.readFileSync(path.join(root, 'native-tests/android/camera-window/LedovaCameraWindowProbe.kt'), 'utf8');
}

export function removeCameraInstrumentation(file, source) {
  transformations = [];
  try {
    const view = file.endsWith('/ExpoCameraView.kt');
    const original = view
      ? '    val cameraProvider = ProcessCameraProvider.awaitInstance(context)\n      camera = cameraProvider.bindToLifecycle(currentActivity, cameraSelector, useCases)\n        observeCameraState(it.cameraInfo)\n          onCameraReady(Unit)\n      onBarcodeScanned(\n        BarcodeScannedEvent('
      : 'import expo.modules.kotlin.functions.Queues\n    Events("onModernBarcodeScanned")';
    instrumentCamera(file, original);
    for (const { before, after } of transformations.reverse()) {
      assert.equal(source.split(after).length - 1, 1, 'Camera probe instrumentation must be intact.');
      source = source.replace(after, before);
    }
    return source;
  } finally {
    transformations = undefined;
  }
}
