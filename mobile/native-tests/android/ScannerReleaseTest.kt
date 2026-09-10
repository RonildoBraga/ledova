package org.example.ledova.releaseprobe

import android.app.Activity
import android.content.Context
import android.hardware.camera2.CameraManager
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import android.widget.TextView
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraState
import androidx.camera.core.UseCase
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

@RunWith(AndroidJUnit4::class)
@androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
class ScannerReleaseTest {
  private val instrumentation = InstrumentationRegistry.getInstrumentation()
  private val device = UiDevice.getInstance(instrumentation)
  private val available = ConcurrentHashMap<String, Boolean>()

  private data class Session(
    val scanner: View,
    val camera: Camera,
    val provider: ProcessCameraProvider,
    val preview: UseCase,
    val analysis: UseCase
  )

  private fun field(value: Any, name: String): Any? =
    value.javaClass.getDeclaredField(name).apply { isAccessible = true }.get(value)

  private fun descendants(view: View): List<View> =
    listOf(view) + if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

  private fun session(): Session? {
    for (view in WindowInspector.getGlobalWindowViews().flatMap { descendants(it) }) {
      if (view.javaClass.name != "org.example.ledova.scanner.ScannerCameraView") continue
      val camera = field(view, "camera") as? Camera ?: continue
      val session = field(view, "session") ?: continue
      return Session(
        view, camera,
        field(session, "provider") as ProcessCameraProvider,
        field(session, "preview") as UseCase,
        field(session, "analysis") as UseCase
      )
    }
    return null
  }

  private fun eventually(message: String, condition: () -> Boolean) {
    val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20)
    do {
      var done = false
      instrumentation.runOnMainSync { done = condition() }
      if (done) return
      Thread.sleep(30)
    } while (System.nanoTime() < deadline)
    fail(message)
  }

  private fun openCamera(): Session {
    var observed: Session? = null
    eventually("Release Expo view never bound and opened a camera") {
      observed = session()
      observed?.let {
        it.provider.isBound(it.preview) && it.provider.isBound(it.analysis) &&
          it.camera.cameraInfo.cameraState.value?.type == CameraState.Type.OPEN &&
          available[Camera2CameraInfo.from(it.camera.cameraInfo).cameraId] == false
      } == true
    }
    return observed!!
  }

  private fun released(previous: Session) {
    val cameraId = Camera2CameraInfo.from(previous.camera.cameraInfo).cameraId
    eventually("Release camera retained a use case, remained open, or did not become available") {
      !previous.provider.isBound(previous.preview) && !previous.provider.isBound(previous.analysis) &&
        previous.camera.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED && available[cameraId] == true
    }
  }

  private fun press(label: String) {
    val button = device.wait(Until.findObject(By.desc(label)), 15000)
    assertNotNull("Missing Release probe checkpoint: $label", button)
    button.click()
  }

  @Test fun releaseExpoAdapterOpensReleasesAndReopensItsOwnCamera() {
    val context = instrumentation.targetContext
    val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    val observer = object : CameraManager.AvailabilityCallback() {
      override fun onCameraAvailable(cameraId: String) { available[cameraId] = true }
      override fun onCameraUnavailable(cameraId: String) { available[cameraId] = false }
    }
    manager.registerAvailabilityCallback(observer, Handler(Looper.getMainLooper()))
    val mode = InstrumentationRegistry.getArguments().getString("reportMode")
    val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)!!
    var scenario: ActivityScenario<Activity>? = null
    try {
      scenario = ActivityScenario.launch<Activity>(intent)
      val first = openCamera()
      press("scanner-probe-cover")
      released(first)
      press("scanner-probe-return")
      val second = openCamera()
      instrumentation.runOnMainSync {
        assertSame(first.scanner, second.scanner)
        assertNotSame(first.preview, second.preview)
        assertNotSame(first.analysis, second.analysis)
      }
      press("scanner-probe-complete")
      released(second)
      val result = device.wait(Until.findObject(By.text(Pattern.compile("NATIVE_PROBE_(PASS|FAIL|REPORT_FAILED)"))), 90000)
      assertNotNull("Release networking probe did not report", result)
      assertEquals(if (mode == "red") "NATIVE_PROBE_FAIL" else "NATIVE_PROBE_PASS", result.text)
    } finally {
      try {
        assertTrue(device.takeScreenshot(File(context.getExternalFilesDir(null), "scanner-release-$mode.png")))
        device.dumpWindowHierarchy(File(context.getExternalFilesDir(null), "scanner-release-$mode.xml"))
        instrumentation.runOnMainSync {
          val statuses = setOf("inactive", "loading", "denied", "failed", "ready", "scanned")
          val current = WindowInspector.getGlobalWindowViews().flatMap { descendants(it) }
            .filterIsInstance<TextView>().map { it.text.toString() }.filter { it in statuses }
          File(context.getExternalFilesDir(null), "scanner-release-$mode-status.txt").writeText(current.joinToString("\n"))
        }
      } finally {
        try { scenario?.close() } finally { manager.unregisterAvailabilityCallback(observer) }
      }
    }
  }
}
