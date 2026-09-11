package org.example.ledova.scanner

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Rect
import android.view.View
import android.view.ViewTreeObserver
import android.widget.FrameLayout
import androidx.annotation.OptIn
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import com.google.common.util.concurrent.ListenableFuture
import com.google.mlkit.vision.common.InputImage

class ScannerCameraView(
  context: Context,
  private val provider: () -> ListenableFuture<ProcessCameraProvider> = { ProcessCameraProvider.getInstance(context) }
) : FrameLayout(context) {
  var onWindowChanged: (Boolean, Int) -> Unit = { _, _ -> }
  var onBarcodeScanned: (String, Int, Int) -> Unit = { _, _, _ -> }
  var onError: (Int, Int) -> Unit = { _, _ -> }
  private var initialized = false
  private var disposed = false
  private var allowed = false
  private var generation = 0
  private var requestedGeneration = -1
  private var scanId = 0
  private var active = false
  private var session: Session? = null
  private val visibleBounds = Rect()
  private var observer: ViewTreeObserver? = null
  private val beforeDraw = ViewTreeObserver.OnPreDrawListener { updateWindow(); true }
  private val mainExecutor = ContextCompat.getMainExecutor(context)
  private val previewView = PreviewView(context).apply {
    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
  }

  internal var camera: Camera? = null
    private set

  private class Session(val generation: Int, val scanId: Int) : LifecycleOwner {
    val registry = LifecycleRegistry(this)
    override fun getLifecycle(): Lifecycle = registry
    var provider: ProcessCameraProvider? = null
    var preview: Preview? = null
    var analysis: ImageAnalysis? = null
    var decoder: QrDecoder? = null
  }

  init {
    addView(previewView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
    initialized = true
  }

  fun request(active: Boolean, generation: Int, scanId: Int) {
    if (disposed) return
    this.active = active
    requestedGeneration = generation
    this.scanId = scanId
    reconcile()
  }

  private fun windowAllowed() =
    !disposed && isAttachedToWindow && hasWindowFocus() && windowVisibility == VISIBLE && isShown &&
      width > 0 && height > 0 && getGlobalVisibleRect(visibleBounds) && !visibleBounds.isEmpty

  private fun updateWindow() {
    if (!initialized) return
    val next = windowAllowed()
    if (allowed != next) {
      allowed = next
      generation += 1
      release()
      onWindowChanged(allowed, generation)
    }
    reconcile()
  }

  private fun admitted() = active && allowed && windowAllowed() && requestedGeneration == generation

  private fun current(candidate: Session) =
    session === candidate && admitted() && candidate.scanId == scanId && candidate.generation == generation

  fun isCurrentScan(generation: Int, scanId: Int): Boolean {
    val candidate = session ?: return false
    return camera != null && current(candidate) && candidate.generation == generation && candidate.scanId == scanId
  }

  private fun reconcile() {
    val existing = session
    if (existing != null && !current(existing)) release()
    if (!admitted() || session != null) return
    if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
      active = false
      onError(generation, scanId)
      return
    }
    val candidate = Session(generation, scanId)
    session = candidate
    try {
      val future = provider()
      future.addListener({
        if (!current(candidate)) return@addListener
        try {
          bind(candidate, future.get())
        } catch (_: Exception) {
          fail(candidate)
        }
      }, mainExecutor)
    } catch (_: Exception) {
      fail(candidate)
    }
  }

  private fun fail(candidate: Session) {
    if (!current(candidate)) return
    active = false
    release()
    onError(candidate.generation, candidate.scanId)
  }

  @OptIn(ExperimentalGetImage::class)
  private fun bind(candidate: Session, provider: ProcessCameraProvider) {
    if (!current(candidate)) return
    candidate.provider = provider
    candidate.registry.currentState = Lifecycle.State.CREATED
    val preview = Preview.Builder().build()
    val analysis = ImageAnalysis.Builder()
      .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
      .build()
    val decoder = QrDecoder(
      mainExecutor,
      { current(candidate) },
      { data -> onBarcodeScanned(data, candidate.generation, candidate.scanId) },
      { fail(candidate) }
    )
    candidate.preview = preview
    candidate.analysis = analysis
    candidate.decoder = decoder
    preview.setSurfaceProvider(previewView.surfaceProvider)
    analysis.setAnalyzer(mainExecutor) { frame ->
      val image = frame.image
      if (!current(candidate) || image == null) {
        frame.close()
      } else {
        try {
          decoder.read(InputImage.fromMediaImage(image, frame.imageInfo.rotationDegrees)) { frame.close() }
        } catch (_: Exception) {
          frame.close()
          fail(candidate)
        }
      }
    }
    camera = provider.bindToLifecycle(candidate, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
    candidate.registry.currentState = Lifecycle.State.RESUMED
  }

  private fun release() {
    val previous = session ?: return
    session = null
    camera = null
    previous.analysis?.clearAnalyzer()
    if (previous.registry.currentState != Lifecycle.State.INITIALIZED) {
      previous.registry.currentState = Lifecycle.State.DESTROYED
    }
    val useCases = listOfNotNull(previous.preview, previous.analysis).toTypedArray()
    if (useCases.isNotEmpty()) previous.provider?.unbind(*useCases)
    previous.decoder?.close()
    previous.preview?.setSurfaceProvider(null)
  }

  fun dispose() {
    disposed = true
    updateWindow()
    release()
  }

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    observer = viewTreeObserver.also { it.addOnPreDrawListener(beforeDraw) }
    updateWindow()
  }

  override fun onDetachedFromWindow() {
    observer?.takeIf { it.isAlive }?.removeOnPreDrawListener(beforeDraw)
    observer = null
    allowed = false
    generation += 1
    release()
    onWindowChanged(false, generation)
    super.onDetachedFromWindow()
  }

  override fun onWindowFocusChanged(hasWindowFocus: Boolean) {
    super.onWindowFocusChanged(hasWindowFocus)
    updateWindow()
  }

  override fun onWindowVisibilityChanged(visibility: Int) {
    super.onWindowVisibilityChanged(visibility)
    updateWindow()
  }

  override fun onVisibilityChanged(changedView: View, visibility: Int) {
    super.onVisibilityChanged(changedView, visibility)
    updateWindow()
  }

  override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
    super.onSizeChanged(width, height, oldWidth, oldHeight)
    updateWindow()
  }
}
