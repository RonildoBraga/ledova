package org.example.ledova.scanner

import android.Manifest
import android.app.Activity
import android.app.Dialog
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.FrameLayout
import androidx.camera.core.CameraState
import androidx.camera.core.UseCase
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.concurrent.futures.CallbackToFutureAdapter
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.TimeUnit

class ScannerTestActivity : Activity() {
  lateinit var container: FrameLayout
  var resumed = false
  override fun onCreate(state: Bundle?) {
    super.onCreate(state)
    container = FrameLayout(this)
    setContentView(container)
  }
  override fun onResume() {
    super.onResume()
    resumed = true
  }
  override fun onPause() {
    resumed = false
    super.onPause()
  }
}

@RunWith(AndroidJUnit4::class)
class ScannerWindowTest {
  @get:Rule val permission = GrantPermissionRule.grant(Manifest.permission.CAMERA)
  private lateinit var scenario: ActivityScenario<ScannerTestActivity>
  private lateinit var activity: ScannerTestActivity
  private lateinit var scanner: ScannerCameraView
  private var allowed = false
  private var generation = -1
  private val dialogs = mutableListOf<Dialog>()
  private val instrumentation = InstrumentationRegistry.getInstrumentation()

  @Before fun open() {
    val intent = Intent(ApplicationProvider.getApplicationContext(), ScannerTestActivity::class.java)
    scenario = ActivityScenario.launch(intent)
    scenario.onActivity { activity = it }
  }

  @After fun close() {
    main {
      dialogs.reversed().forEach { it.dismiss() }
      activity.container.removeAllViews()
    }
    scenario.close()
  }

  private fun main(action: () -> Unit) = instrumentation.runOnMainSync(action)

  private fun eventually(message: String, condition: () -> Boolean) {
    val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15)
    do {
      var done = false
      main { done = condition() }
      if (done) return
      Thread.sleep(30)
    } while (System.nanoTime() < deadline)
    fail(message)
  }

  private fun observe(view: ScannerCameraView) {
    scanner = view
    scanner.onWindowChanged = { visible, revision ->
      allowed = visible
      generation = revision
    }
  }

  private fun attach() {
    main {
      observe(ScannerCameraView(activity))
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("scanner window never focused") { allowed }
  }

  private fun start(scanId: Int = 1) {
    main { scanner.request(true, generation, scanId) }
    eventually("camera never opened") { scanner.camera?.cameraInfo?.cameraState?.value?.type == CameraState.Type.OPEN }
    main {
      assertTrue(scanner.isCurrentScan(generation, scanId))
      assertFalse(scanner.isCurrentScan(generation - 1, scanId))
      assertFalse(scanner.isCurrentScan(generation, scanId - 1))
    }
  }

  private fun useCases(view: ScannerCameraView): List<UseCase> {
    val session = ScannerCameraView::class.java.getDeclaredField("session").apply { isAccessible = true }.get(view)!!
    return listOf("preview", "analysis").map {
      session.javaClass.getDeclaredField(it).apply { isAccessible = true }.get(session) as UseCase
    }
  }

  private fun cover(): Dialog {
    lateinit var dialog: Dialog
    main {
      dialog = Dialog(activity)
      dialog.setContentView(FrameLayout(activity))
      dialogs.add(dialog)
      dialog.show()
    }
    eventually("covered window retained focus") { !allowed }
    return dialog
  }

  @Test fun focusLossClosesCameraWhileActivityStaysResumedAndNeedsFreshAdmission() {
    attach()
    start()
    val previous = scanner.camera!!
    val oldGeneration = generation
    val dialog = cover()
    eventually("camera not closed on focus loss") { previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
    main {
      assertTrue(activity.resumed)
      assertNull(scanner.camera)
      assertFalse(scanner.isCurrentScan(oldGeneration, 1))
      dialog.dismiss()
    }
    eventually("focus did not return") { allowed }
    main {
      scanner.request(true, oldGeneration, 1)
      assertNull(scanner.camera)
    }
    start(2)
  }

  @Test fun modalScannerUsesItsOwnWindowAndClosesForASecondModal() {
    main {
      val dialog = Dialog(activity)
      observe(ScannerCameraView(activity))
      dialog.setContentView(scanner, FrameLayout.LayoutParams(500, 500))
      dialogs.add(dialog)
      dialog.show()
    }
    eventually("scanner modal never focused") { allowed && !activity.container.hasWindowFocus() }
    start()
    val previous = scanner.camera!!
    cover()
    eventually("modal camera not closed") { previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
    main { assertTrue(activity.resumed); assertNull(scanner.camera) }
  }

  @Test fun hiddenParentAndDetachmentCloseTheCamera() {
    attach()
    start()
    val previous = scanner.camera!!
    main { activity.container.visibility = View.INVISIBLE }
    eventually("hidden camera not closed") { !allowed && previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
    main { activity.container.visibility = View.VISIBLE }
    eventually("visible window did not return") { allowed }
    start(2)
    val reopened = scanner.camera!!
    main { activity.container.removeView(scanner) }
    eventually("detached camera not closed") { !allowed && reopened.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
  }

  @Test fun inactiveAndCompletedPreviewsKeepTheWindowObserverWithoutOpeningCamera() {
    attach()
    main { scanner.request(false, generation, 1); assertNull(scanner.camera) }
    start(2)
    val previous = scanner.camera!!
    main { scanner.request(false, generation, 2) }
    eventually("inactive preview did not close") { previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
    val dialog = cover()
    main { dialog.dismiss() }
    eventually("observer was removed with preview") { allowed }
    main { assertNull(scanner.camera) }
  }

  @Test fun movingOutsideTheVisibleParentClosesTheCamera() {
    attach()
    start()
    val previous = scanner.camera!!
    main { scanner.translationY = 10000f }
    eventually("clipped camera not closed") { !allowed && previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
    main { scanner.translationY = 0f }
    eventually("visible scanner did not return") { allowed }
    start(2)
  }

  @Test fun backgroundingTheActivityClosesTheCamera() {
    attach()
    start()
    val previous = scanner.camera!!
    scenario.moveToState(Lifecycle.State.CREATED)
    eventually("background camera not closed") { !allowed && previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED }
    scenario.moveToState(Lifecycle.State.RESUMED)
    eventually("foreground scanner did not return") { allowed }
    start(2)
  }

  @Test fun delayedProviderCannotBindAfterWindowLossOrAfterRegainWithOldProps() {
    val provider = ProcessCameraProvider.getInstance(activity).get(15, TimeUnit.SECONDS)
    lateinit var completer: CallbackToFutureAdapter.Completer<ProcessCameraProvider>
    val future = CallbackToFutureAdapter.getFuture<ProcessCameraProvider> { completer = it; "delayed-camera" }
    var requested = false
    main {
      observe(ScannerCameraView(activity) { requested = true; future })
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("scanner window never focused") { allowed }
    main { scanner.request(true, generation, 1); assertTrue(requested); assertNull(scanner.camera) }
    val dialog = cover()
    main { dialog.dismiss() }
    eventually("focus did not return") { allowed }
    completer.set(provider)
    instrumentation.waitForIdleSync()
    main { assertNull(scanner.camera) }
    start(2)
  }

  @Test fun delayedProviderCannotBindAfterDisposal() {
    val provider = ProcessCameraProvider.getInstance(activity).get(15, TimeUnit.SECONDS)
    lateinit var completer: CallbackToFutureAdapter.Completer<ProcessCameraProvider>
    val future = CallbackToFutureAdapter.getFuture<ProcessCameraProvider> { completer = it; "disposed-camera" }
    main {
      observe(ScannerCameraView(activity) { future })
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("scanner window never focused") { allowed }
    main { scanner.request(true, generation, 1); scanner.dispose() }
    completer.set(provider)
    instrumentation.waitForIdleSync()
    main { assertNull(scanner.camera); assertFalse(allowed) }
    main {
      activity.container.removeView(scanner)
      observe(ScannerCameraView(activity))
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("replacement observer never focused") { allowed }
    start()
  }

  @Test fun lateProviderFromAnOlderAdmissionCannotReplaceTheCurrentCamera() {
    val ready = ProcessCameraProvider.getInstance(activity)
    val provider = ready.get(15, TimeUnit.SECONDS)
    lateinit var completer: CallbackToFutureAdapter.Completer<ProcessCameraProvider>
    val delayed = CallbackToFutureAdapter.getFuture<ProcessCameraProvider> { completer = it; "older-admission" }
    var requests = 0
    main {
      observe(ScannerCameraView(activity) { if (requests++ == 0) delayed else ready })
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("scanner window never focused") { allowed }
    main { scanner.request(true, generation, 1); assertNull(scanner.camera) }
    start(2)
    val replacement = scanner.camera!!
    lateinit var owned: List<UseCase>
    main { owned = useCases(scanner); assertTrue(owned.all { provider.isBound(it) }) }
    completer.set(provider)
    instrumentation.waitForIdleSync()
    main {
      assertSame(replacement, scanner.camera)
      assertTrue(scanner.isCurrentScan(generation, 2))
      assertTrue(owned.all { provider.isBound(it) })
    }
  }

  @Test fun disposedViewLateCompletionAndTeardownCannotCloseAReplacementView() {
    val provider = ProcessCameraProvider.getInstance(activity).get(15, TimeUnit.SECONDS)
    lateinit var completer: CallbackToFutureAdapter.Completer<ProcessCameraProvider>
    val delayed = CallbackToFutureAdapter.getFuture<ProcessCameraProvider> { completer = it; "older-view" }
    lateinit var retired: ScannerCameraView
    main {
      observe(ScannerCameraView(activity) { delayed })
      retired = scanner
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("scanner window never focused") { allowed }
    main {
      scanner.request(true, generation, 1)
      scanner.dispose()
      activity.container.removeView(scanner)
      observe(ScannerCameraView(activity))
      activity.container.addView(scanner, FrameLayout.LayoutParams(500, 500))
    }
    eventually("replacement window never focused") { allowed }
    start(2)
    val replacement = scanner.camera!!
    lateinit var owned: List<UseCase>
    main { owned = useCases(scanner); assertTrue(owned.all { provider.isBound(it) }) }
    completer.set(provider)
    instrumentation.waitForIdleSync()
    main {
      retired.dispose()
      assertNull(retired.camera)
      assertSame(replacement, scanner.camera)
      assertTrue(owned.all { provider.isBound(it) })
      assertTrue(scanner.isCurrentScan(generation, 2))
    }
  }

  @Test fun rapidNativeFocusCycleCannotReuseUnchangedJavaScriptAdmission() {
    attach()
    start()
    val previous = scanner.camera!!
    val admittedGeneration = generation
    val dialog = cover()
    main { dialog.dismiss() }
    eventually("focus did not return") { allowed }
    main {
      assertTrue(generation >= admittedGeneration + 2)
      assertFalse(scanner.isCurrentScan(admittedGeneration, 1))
      scanner.request(true, admittedGeneration, 1)
      assertNull(scanner.camera)
    }
    eventually("retired camera reopened without fresh admission") {
      previous.cameraInfo.cameraState.value?.type == CameraState.Type.CLOSED
    }
    start(2)
  }
}
