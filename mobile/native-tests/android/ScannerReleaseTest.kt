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
import java.lang.reflect.Field
import java.util.Collections
import java.util.IdentityHashMap
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

@RunWith(AndroidJUnit4::class)
@androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
class ScannerReleaseTest {
  private val instrumentation = InstrumentationRegistry.getInstrumentation()
  private val device = UiDevice.getInstance(instrumentation)
  private val available = ConcurrentHashMap<String, Boolean>()
  private var stage = "launch"
  private var lastObservation = "not sampled"
  private val checkpoints = mutableListOf<String>()

  private data class Session(
    val scanner: View,
    val camera: Camera,
    val provider: ProcessCameraProvider,
    val preview: UseCase,
    val analysis: UseCase
  )

  private data class JsState(val status: String, val generation: Int, val scanId: Int, val scans: Int)
  private data class Query(val generation: Int, val scanId: Int, val admitted: Boolean)
  private data class CameraObservation(
    val cameraId: String,
    val previewBound: Boolean,
    val analysisBound: Boolean,
    val state: CameraState.Type?,
    val available: Boolean?,
    val attached: Boolean,
    val capturedViewPresent: Boolean,
    val nativeViews: Int,
    val js: JsState?
  )

  private fun enterStage(value: String) {
    stage = value
    lastObservation = "not sampled"
    checkpoints.add("stage=$value")
    println("SCANNER_PROOF stage=$value")
  }

  private fun member(value: Any, name: String): Field {
    var type: Class<*>? = value.javaClass
    while (type != null) {
      try {
        return type.getDeclaredField(name).apply { isAccessible = true }
      } catch (_: NoSuchFieldException) {
        type = type.superclass
      }
    }
    error("Missing pinned probe field: $name")
  }

  private inner class FieldLease(private val owner: Any, name: String) : AutoCloseable {
    private val member = member(owner, name)
    val original = member.get(owner)
    fun replace(value: Any) {
      member.set(owner, value)
      assertSame(value, member.get(owner))
    }
    override fun close() {
      member.set(owner, original)
      assertSame(original, member.get(owner))
    }
  }

  private fun getter(value: Any, name: String): Any = requireNotNull(value.javaClass.getMethod(name).invoke(value))

  private fun queryFunction(scanner: View): Any {
    val owner = scanner.parent
    assertEquals("org.example.ledova.scanner.ScannerExpoView", owner.javaClass.name)
    val registry = getter(getter(owner, "getAppContext"), "getRegistry")
    val holder = requireNotNull(registry.javaClass.getMethod("getModuleHolder", String::class.java).invoke(registry, "LedovaScanner"))
    val definitions = getter(getter(holder, "getDefinition"), "getViewManagerDefinitions") as Map<*, *>
    val functions = definitions.values.flatMap { getter(requireNotNull(it), "getAsyncFunctions") as List<*> }
    val seen = Collections.newSetFromMap(IdentityHashMap<Any, Boolean>())
    return functions.filterNotNull().filter { seen.add(it) }.single { member(it, "name").get(it) == "isCurrentScan" }.also {
      assertEquals("expo.modules.kotlin.functions.UntypedAsyncFunctionComponent", it.javaClass.name)
    }
  }

  @Suppress("UNCHECKED_CAST")
  private inner class NativeQueries(scanner: View) : AutoCloseable {
    private val owner = scanner.parent
    private val lease = FieldLease(queryFunction(scanner), "body")
    private val original = lease.original as (Array<out Any?>) -> Any?
    val observed = mutableListOf<Query>()
    init {
      val recorder: (Array<out Any?>) -> Any? = { args ->
        val admitted = original(args)
        assertTrue(admitted is Boolean)
        if (args[0] === owner) {
          assertSame(Looper.getMainLooper(), Looper.myLooper())
          observed.add(Query(args[1] as Int, args[2] as Int, admitted as Boolean))
        }
        admitted
      }
      try { lease.replace(recorder) } catch (error: Throwable) { lease.close(); throw error }
    }
    override fun close() = lease.close()
  }

  @Suppress("UNCHECKED_CAST")
  private inner class HeldWindows(scanner: View) : AutoCloseable {
    private val lease = FieldLease(scanner, "onWindowChanged")
    private val original = lease.original as (Boolean, Int) -> Unit
    val events = mutableListOf<Pair<Boolean, Int>>()
    init {
      val hold: (Boolean, Int) -> Unit = { allowed, generation -> events.add(allowed to generation) }
      try { lease.replace(hold) } catch (error: Throwable) { lease.close(); throw error }
    }
    fun flush() {
      lease.close()
      val pending = events.toList()
      events.clear()
      pending.forEach { original(it.first, it.second) }
    }
    override fun close() {
      try { lease.close() } finally { events.clear() }
    }
  }

  private fun <T> withNativeQueries(scanner: View, action: (NativeQueries) -> T): T {
    lateinit var queries: NativeQueries
    instrumentation.runOnMainSync { queries = NativeQueries(scanner) }
    try { return action(queries) } finally { instrumentation.runOnMainSync { queries.close() } }
  }

  private fun <T> withHeldWindows(scanner: View, action: (HeldWindows) -> T): T {
    lateinit var windows: HeldWindows
    instrumentation.runOnMainSync { windows = HeldWindows(scanner) }
    try { return action(windows) } finally { instrumentation.runOnMainSync { windows.close() } }
  }

  private fun field(value: Any, name: String): Any? =
    value.javaClass.getDeclaredField(name).apply { isAccessible = true }.get(value)

  private fun descendants(view: View): List<View> =
    listOf(view) + if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

  private fun windowViews(): List<View> {
    val seen = Collections.newSetFromMap(IdentityHashMap<View, Boolean>())
    return WindowInspector.getGlobalWindowViews().flatMap { descendants(it) }.filter { seen.add(it) }
  }

  private fun jsState(): JsState? {
    val value = windowViews().filterIsInstance<TextView>()
      .singleOrNull { it.contentDescription?.toString() == "scanner-probe-state" }?.text?.toString() ?: return null
    val parts = value.split('|')
    if (parts.size != 4) return null
    return JsState(parts[0], parts[1].toInt(), parts[2].toInt(), parts[3].toInt())
  }

  @Suppress("UNCHECKED_CAST")
  private fun capturedBarcode(session: Session): () -> Unit {
    val callback = field(session.scanner, "onBarcodeScanned") as (String, Int, Int) -> Unit
    val owner = requireNotNull(field(session.scanner, "session"))
    val generation = field(owner, "generation") as Int
    val scanId = field(owner, "scanId") as Int
    return { callback("synthetic-scanner-proof", generation, scanId) }
  }

  private fun restoredAfterFailure(scanner: View) {
    lateinit var function: Any
    var originalBody: Any? = null
    var originalWindow: Any? = null
    instrumentation.runOnMainSync {
      function = queryFunction(scanner)
      originalBody = member(function, "body").get(function)
      originalWindow = field(scanner, "onWindowChanged")
    }
    val failure = IllegalStateException("synthetic reflection cleanup control")
    try {
      withNativeQueries(scanner) {
        withHeldWindows(scanner) { throw failure }
      }
      fail("deliberate control failure did not propagate")
    } catch (error: IllegalStateException) {
      assertSame(failure, error)
    }
    instrumentation.runOnMainSync {
      assertSame(originalBody, member(function, "body").get(function))
      assertSame(originalWindow, field(scanner, "onWindowChanged"))
    }
    println("SCANNER_PROOF reflection references restored after deliberate failure")
  }

  private fun session(): Session? {
    for (view in windowViews()) {
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

  private fun observe(previous: Session): CameraObservation {
    val cameraId = Camera2CameraInfo.from(previous.camera.cameraInfo).cameraId
    val views = windowViews()
    return CameraObservation(
      cameraId, previous.provider.isBound(previous.preview), previous.provider.isBound(previous.analysis),
      previous.camera.cameraInfo.cameraState.value?.type, available[cameraId], previous.scanner.isAttachedToWindow,
      views.any { it === previous.scanner },
      views.count { it.javaClass.name == "org.example.ledova.scanner.ScannerCameraView" }, jsState()
    ).also { lastObservation = it.toString() }
  }

  private fun eventually(message: String, condition: () -> Boolean) {
    val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20)
    do {
      var done = false
      instrumentation.runOnMainSync { done = condition() }
      if (done) {
        checkpoints.add("stage=$stage conditionSatisfied=true observed=$lastObservation")
        return
      }
      Thread.sleep(30)
    } while (System.nanoTime() < deadline)
    fail("stage=$stage: $message; observed=$lastObservation")
  }

  private fun openCamera(): Session {
    var observed: Session? = null
    eventually("Release Expo view never bound and opened a camera") {
      observed = session()
      observed?.let {
        val current = observe(it)
        current.previewBound && current.analysisBound && current.state == CameraState.Type.OPEN &&
          current.available == false
      } == true
    }
    return observed!!
  }

  private fun released(previous: Session) {
    eventually("Release camera retained a use case, remained open, or did not become available") {
      val current = observe(previous)
      !current.previewBound && !current.analysisBound && current.state == CameraState.Type.CLOSED && current.available == true
    }
  }

  private fun unmounted(previous: Session, kind: String) {
    enterStage("$kind-js-unmount-ack")
    eventually("JavaScript did not acknowledge $kind scanner unmount") {
      observe(previous)
      windowViews().any {
        it.contentDescription?.toString() == "scanner-probe-$kind-unmounted"
      }
    }
    enterStage("$kind-native-view-absence")
    eventually("$kind scanner view remained attached or present after JavaScript acknowledgement") {
      val current = observe(previous)
      !current.attached && !current.capturedViewPresent && current.nativeViews == 0
    }
    enterStage("$kind-unmount-release")
    released(previous)
    println("SCANNER_PROOF $kind scanner unmounted and released; observed=$lastObservation")
  }

  private fun press(label: String) {
    val button = device.wait(Until.findObject(By.desc(label)), 15000)
    assertNotNull("stage=$stage: Missing Release probe checkpoint: $label", button)
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
      enterStage("active-unmount-open")
      val active = openCamera()
      instrumentation.runOnMainSync {
        val ready = requireNotNull(jsState())
        assertEquals("ready", ready.status)
        assertEquals(0, ready.scans)
        assertEquals(true, field(active.scanner, "active"))
      }
      enterStage("active-unmount-request")
      press("scanner-probe-unmount-active")
      unmounted(active, "active")
      enterStage("remount-request")
      press("scanner-probe-remount")
      enterStage("remount-open")
      val first = openCamera()
      assertNotSame(active.scanner, first.scanner)
      enterStage("recorder-restoration-control")
      restoredAfterFailure(first.scanner)
      withNativeQueries(first.scanner) { queries ->
        lateinit var before: JsState
        lateinit var queued: () -> Unit
        instrumentation.runOnMainSync {
          before = requireNotNull(jsState())
          assertEquals("ready", before.status)
          assertEquals(0, before.scans)
          queued = capturedBarcode(first)
        }
        withHeldWindows(first.scanner) { windows ->
          enterStage("queued-cover-request")
          press("scanner-probe-cover")
          enterStage("queued-cover-release")
          released(first)
          enterStage("queued-delivery-loss")
          instrumentation.runOnMainSync {
            assertTrue(windows.events.any { !it.first })
            assertEquals(before, jsState())
            queued()
          }
          eventually("queued loss event did not finish the actual native admission query") { queries.observed.size == 1 }
          instrumentation.runOnMainSync {
            assertEquals(Query(before.generation, before.scanId, false), queries.observed.single())
            assertEquals(before, jsState())
          }
          println("SCANNER_PROOF queued pre-loss tuple native=false before JavaScript window notification")
          enterStage("queued-return-request")
          press("scanner-probe-return")
          enterStage("queued-native-regain")
          eventually("native quick regain did not retire the old admission") {
            first.scanner.hasWindowFocus() && windows.events.lastOrNull()?.first == true &&
              (field(first.scanner, "generation") as Int) >= before.generation + 2
          }
          instrumentation.runOnMainSync {
            assertNull(field(first.scanner, "session"))
            assertNull(field(first.scanner, "camera"))
            assertEquals(before, jsState())
            queued()
          }
          enterStage("queued-delivery-regain")
          eventually("queued regain event did not finish the actual native admission query") { queries.observed.size == 2 }
          instrumentation.runOnMainSync {
            assertEquals(Query(before.generation, before.scanId, false), queries.observed.last())
            assertEquals(before, jsState())
            windows.flush()
          }
          println("SCANNER_PROOF quick native loss/regain still refuses the original tuple")
        }
        enterStage("fresh-open")
        val second = openCamera()
        lateinit var fresh: JsState
        lateinit var live: () -> Unit
        enterStage("live-delivery-finish")
        instrumentation.runOnMainSync {
          assertSame(first.scanner, second.scanner)
          assertNotSame(first.preview, second.preview)
          assertNotSame(first.analysis, second.analysis)
          fresh = requireNotNull(jsState())
          assertEquals("ready", fresh.status)
          assertTrue(fresh.generation > before.generation)
          assertTrue(fresh.scanId != before.scanId)
          live = capturedBarcode(second)
          live()
        }
        eventually("live native acceptance did not call the actual scanner finish exactly once") {
          queries.observed.size == 3 && jsState()?.let { it.status == "scanned" && it.scans == 1 } == true
        }
        instrumentation.runOnMainSync {
          assertEquals(Query(fresh.generation, fresh.scanId, true), queries.observed.last())
        }
        enterStage("live-finish-release")
        released(second)
        println("SCANNER_PROOF unchanged live tuple native=true finishes once and releases")
        enterStage("completed-cover-request")
        press("scanner-probe-cover")
        eventually("completed native scanner did not observe window loss") { !first.scanner.hasWindowFocus() }
        enterStage("completed-return-request")
        press("scanner-probe-return")
        enterStage("completed-refocus")
        eventually("completed scanner did not preserve finish after refocus") {
          first.scanner.hasWindowFocus() && jsState()?.let { it.status == "scanned" && it.scans == 1 } == true
        }
        instrumentation.runOnMainSync {
          assertNull(field(first.scanner, "session"))
          assertNull(field(first.scanner, "camera"))
          assertEquals(false, field(first.scanner, "active"))
          assertFalse(second.provider.isBound(second.preview))
          assertFalse(second.provider.isBound(second.analysis))
          assertEquals(CameraState.Type.CLOSED, second.camera.cameraInfo.cameraState.value?.type)
        }
        println("SCANNER_PROOF completed scanner remains mounted and unbound after refocus")
        enterStage("completed-unmount-request")
        press("scanner-probe-complete")
        unmounted(second, "completed")
      }
      enterStage("network-report-request")
      press("scanner-probe-report")
      enterStage("network-report")
      val result = device.wait(Until.findObject(By.text(Pattern.compile("NATIVE_PROBE_(PASS|FAIL|REPORT_FAILED)"))), 90000)
      assertNotNull("Release networking probe did not report", result)
      assertEquals(if (mode == "red") "NATIVE_PROBE_FAIL" else "NATIVE_PROBE_PASS", result.text)
    } finally {
      try {
        assertTrue(device.takeScreenshot(File(context.getExternalFilesDir(null), "scanner-release-$mode.png")))
        device.dumpWindowHierarchy(File(context.getExternalFilesDir(null), "scanner-release-$mode.xml"))
        instrumentation.runOnMainSync {
          val statuses = setOf("inactive", "loading", "denied", "failed", "ready", "scanned")
          val current = windowViews()
            .filterIsInstance<TextView>().map { it.text.toString() }.filter { it in statuses }
          File(context.getExternalFilesDir(null), "scanner-release-$mode-status.txt").writeText(
            (current + checkpoints + "lastStage=$stage" + "lastObservation=$lastObservation").joinToString("\n")
          )
        }
      } finally {
        try { scenario?.close() } finally { manager.unregisterAvailabilityCallback(observer) }
      }
    }
  }
}
