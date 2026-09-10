package expo.modules.camera

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.hardware.camera2.CameraManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraInfo
import androidx.camera.core.CameraState
import androidx.camera.core.UseCase
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LiveData
import androidx.lifecycle.Observer
import expo.modules.camera.utils.BarCodeScannerResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout

object LedovaCameraWindowProbe {
  private class Registration(val state: LiveData<CameraState>, val observer: Any)

  private class Entry(val id: Int, val view: ExpoCameraView) {
    var provider: ProcessCameraProvider? = null
    var camera: Camera? = null
    var useCases: List<UseCase> = emptyList()
    var observer: Observer<CameraState>? = null
    val siblingObservers = mutableListOf<Pair<LiveData<CameraState>, Observer<CameraState>>>()
    var siblingState = "NONE"
    var observersBefore = emptyList<Any>()
    val registrations = mutableListOf<Registration>()
    var boundFields = emptyList<Any?>()
    var cameraId = "NONE"
    var manager: CameraManager? = null
    var availabilityCallback: CameraManager.AvailabilityCallback? = null
    val availability = mutableListOf<String>()
    var state = "NONE"
    var attempts = 0
    var binds = 0
    var ready = 0
    var barcodes = 0
    var waiting = false
    var awaitedRatio = "NONE"
    var gatedRatio = "NONE"
    var gate: CompletableDeferred<Unit>? = null
    var parent: ViewGroup? = null
    var position = 0
    var owner: View? = null
  }

  private val entries = mutableListOf<Entry>()
  private var nextId = 0
  private var gateNext = false
  private var cover: Dialog? = null

  private fun entry(view: ExpoCameraView): Entry = entries.firstOrNull { it.view === view }
    ?: Entry(++nextId, view).also { entries.add(it) }

  private fun entry(id: Int): Entry = entries.single { it.id == id }

  fun arm() {
    check(!gateNext)
    gateNext = true
  }

  suspend fun afterProvider(view: ExpoCameraView, provider: ProcessCameraProvider) {
    val item = entry(view)
    item.provider = provider
    item.awaitedRatio = view.ratio?.name ?: "DEFAULT"
    var parent = view.parent
    while (parent is View) {
      if (parent.javaClass.name == "expo.modules.ledovacamerawindow.LedovaCameraWindowView") {
        item.owner = parent
        break
      }
      parent = parent.parent
    }
    if (gateNext) {
      gateNext = false
      item.gate = CompletableDeferred()
      item.waiting = true
      item.gatedRatio = item.awaitedRatio
      try {
        item.gate!!.await()
      } finally {
        item.waiting = false
      }
    }
  }

  fun bound(
    view: ExpoCameraView,
    provider: ProcessCameraProvider,
    camera: Camera,
    useCases: List<UseCase>,
    activity: Activity
  ) {
    val item = entry(view)
    removeProbeObservers(item)
    item.camera = camera
    item.provider = provider
    item.useCases = useCases
    item.binds += 1
    item.boundFields = fields(view)
    val observer = Observer<CameraState> { item.state = it.type.name }
    item.observer = observer
    camera.cameraInfo.cameraState.observeForever(observer)
    val state = camera.cameraInfo.cameraState
    if (item.siblingObservers.none { it.first === state }) {
      val siblingObserver = Observer<CameraState> {
        if (item.camera?.cameraInfo?.cameraState === state) item.siblingState = it.type.name
      }
      item.siblingObservers.add(state to siblingObserver)
      state.observe(activity as LifecycleOwner, siblingObserver)
    }
    observeAvailability(item, camera.cameraInfo)
  }

  private fun fields(view: ExpoCameraView): List<Any?> = listOf(
    "imageCaptureUseCase", "imageAnalysisUseCase", "recorder"
  ).map { name ->
    ExpoCameraView::class.java.getDeclaredField(name).also { it.isAccessible = true }.get(view)
  }

  private fun observers(state: LiveData<CameraState>): List<Any> {
    val field = LiveData::class.java.getDeclaredField("mObservers").also { it.isAccessible = true }
    return (field.get(state) as Iterable<*>).map { (it as Map.Entry<*, *>).key!! }
  }

  private fun present(registration: Registration): Boolean =
    observers(registration.state).any { it === registration.observer }

  fun beforeObserve(view: ExpoCameraView, info: CameraInfo) {
    entry(view).observersBefore = observers(info.cameraState)
  }

  fun afterObserve(view: ExpoCameraView, info: CameraInfo) {
    val item = entry(view)
    val added = observers(info.cameraState).filter { observer -> item.observersBefore.none { it === observer } }
    item.registrations.addAll(added.map { Registration(info.cameraState, it) })
    item.observersBefore = emptyList()
  }

  @OptIn(ExperimentalCamera2Interop::class)
  private fun observeAvailability(item: Entry, info: CameraInfo) {
    val cameraId = Camera2CameraInfo.from(info).cameraId
    if (item.availabilityCallback != null) {
      check(item.cameraId == cameraId)
      return
    }
    item.cameraId = cameraId
    val manager = item.view.context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    val callback = object : CameraManager.AvailabilityCallback() {
      override fun onCameraAvailable(id: String) {
        if (id == cameraId) item.availability.add("AVAILABLE")
      }
      override fun onCameraUnavailable(id: String) {
        if (id == cameraId) item.availability.add("UNAVAILABLE")
      }
    }
    item.manager = manager
    item.availabilityCallback = callback
    manager.registerAvailabilityCallback(callback, Handler(Looper.getMainLooper()))
  }

  private fun removeProbeObservers(item: Entry) {
    item.camera?.cameraInfo?.cameraState?.let { state ->
      item.observer?.let { state.removeObserver(it) }
    }
    item.observer = null
  }

  fun attempt(view: ExpoCameraView) { entry(view).attempts += 1 }
  fun ready(view: ExpoCameraView) { entry(view).ready += 1 }
  fun barcode(view: ExpoCameraView) { entry(view).barcodes += 1 }
  fun release(id: Int) { entry(id).gate?.complete(Unit) }
  fun retire(id: Int) { entry(id).view.cleanupCamera() }
  fun pause(id: Int) { entry(id).view.pausePreview() }

  fun scan(id: Int) {
    val method = ExpoCameraView::class.java.getDeclaredMethod("onBarcodeScanned", BarCodeScannerResult::class.java)
    method.isAccessible = true
    method.invoke(
      entry(id).view,
      BarCodeScannerResult(256, "synthetic-camera-window", "synthetic-camera-window", Bundle(), mutableListOf(), 100, 100)
    )
  }

  fun detach(id: Int) {
    val item = entry(id)
    val parent = item.view.parent as ViewGroup
    item.parent = parent
    item.position = parent.indexOfChild(item.view)
    parent.removeView(item.view)
  }

  fun reattach(id: Int) {
    val item = entry(id)
    item.parent!!.addView(item.view, item.position)
    item.parent = null
  }

  fun visibility(id: Int, visible: Boolean) {
    entry(id).owner!!.visibility = if (visible) View.VISIBLE else View.INVISIBLE
  }

  fun showCover(activity: Activity) {
    check(cover == null)
    cover = Dialog(activity).also { dialog ->
      dialog.setContentView(TextView(activity).apply { text = "Synthetic camera focus cover" })
      dialog.show()
    }
  }

  fun hideCover() {
    cover?.dismiss()
    cover = null
  }

  suspend fun cycleFocus(activity: Activity, id: Int): Map<String, Any> {
    val item = entry(id)
    val attachedAtStart = item.view.isAttachedToWindow
    showCover(activity)
    withTimeout(5000) { while (item.view.hasWindowFocus()) delay(10) }
    val lost = !item.view.hasWindowFocus()
    hideCover()
    withTimeout(5000) { while (!item.view.hasWindowFocus()) delay(10) }
    delay(100)
    return mapOf(
      "lost" to lost,
      "focused" to item.view.hasWindowFocus(),
      "bound" to item.useCases.any { item.provider?.isBound(it) == true },
      "binds" to item.binds,
      "attachedAtStart" to attachedAtStart,
      "attachedAtReturn" to item.view.isAttachedToWindow
    )
  }

  fun snapshot(activity: Activity): Map<String, Any> = mapOf(
    "activityState" to (activity as LifecycleOwner).lifecycle.currentState.name,
    "activityFocused" to activity.hasWindowFocus(),
    "entries" to entries.map { item -> mapOf(
      "id" to item.id,
      "waiting" to item.waiting,
      "awaitedRatio" to item.awaitedRatio,
      "gatedRatio" to item.gatedRatio,
      "attempts" to item.attempts,
      "binds" to item.binds,
      "ready" to item.ready,
      "barcodes" to item.barcodes,
      "state" to item.state,
      "siblingState" to item.siblingState,
      "fieldsMatchBound" to (item.boundFields.isNotEmpty() && item.boundFields.all { it != null } && fields(item.view).zip(item.boundFields).all { it.first === it.second }),
      "boundCapture" to (item.boundFields.getOrNull(0)?.let { field -> item.useCases.any { it === field && item.provider?.isBound(it) == true } } == true),
      "boundAnalyzer" to (item.boundFields.getOrNull(1)?.let { field -> item.useCases.any { it === field && item.provider?.isBound(it) == true } } == true),
      "registeredObservers" to item.registrations.size,
      "presentObservers" to item.registrations.count { present(it) },
      "retiredObserversPresent" to item.registrations.dropLast(1).count { present(it) },
      "probeObserverPresent" to (item.camera?.cameraInfo?.cameraState?.let { state -> observers(state).any { it === item.observer } } == true),
      "siblingObserverPresent" to (item.siblingObservers.isNotEmpty() && item.siblingObservers.all { (state, observer) -> observers(state).any { it === observer } }),
      "cameraId" to item.cameraId,
      "availability" to item.availability.toList(),
      "bound" to item.useCases.any { item.provider?.isBound(it) == true },
      "attached" to item.view.isAttachedToWindow,
      "focused" to item.view.hasWindowFocus(),
      "detachedByProbe" to (item.parent != null)
    ) }
  )

  fun reset() {
    hideCover()
    check(entries.none { it.waiting })
    for (item in entries) {
      item.view.cleanupCamera()
      removeProbeObservers(item)
      item.siblingObservers.forEach { (state, observer) -> state.removeObserver(observer) }
      item.siblingObservers.clear()
      item.availabilityCallback?.let { item.manager?.unregisterAvailabilityCallback(it) }
    }
    entries.clear()
    gateNext = false
  }
}
