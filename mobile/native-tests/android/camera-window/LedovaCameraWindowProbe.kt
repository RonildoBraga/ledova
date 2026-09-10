package expo.modules.camera

import android.app.Activity
import android.app.Dialog
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.camera.core.Camera
import androidx.camera.core.CameraState
import androidx.camera.core.UseCase
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.Observer
import expo.modules.camera.utils.BarCodeScannerResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout

object LedovaCameraWindowProbe {
  private class Entry(val id: Int, val view: ExpoCameraView) {
    var provider: ProcessCameraProvider? = null
    var camera: Camera? = null
    var useCases: List<UseCase> = emptyList()
    var observer: Observer<CameraState>? = null
    var state = "NONE"
    var attempts = 0
    var binds = 0
    var ready = 0
    var barcodes = 0
    var waiting = false
    var awaitedRatio = "NONE"
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
    useCases: List<UseCase>
  ) {
    val item = entry(view)
    item.camera?.cameraInfo?.cameraState?.let { state -> item.observer?.let { state.removeObserver(it) } }
    item.camera = camera
    item.provider = provider
    item.useCases = useCases
    item.binds += 1
    val observer = Observer<CameraState> { item.state = it.type.name }
    item.observer = observer
    camera.cameraInfo.cameraState.observeForever(observer)
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
      "attempts" to item.attempts,
      "binds" to item.binds,
      "ready" to item.ready,
      "barcodes" to item.barcodes,
      "state" to item.state,
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
      item.camera?.cameraInfo?.cameraState?.let { state -> item.observer?.let { state.removeObserver(it) } }
    }
    entries.clear()
    gateNext = false
  }
}
