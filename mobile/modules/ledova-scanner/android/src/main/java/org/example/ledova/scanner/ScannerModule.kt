package org.example.ledova.scanner

import android.content.Context
import android.view.ViewGroup
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView

class ScannerModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("LedovaScanner")
    View(ScannerExpoView::class) {
      Events("onWindowChanged", "onBarcodeScanned", "onMountError")
      Prop("active") { view: ScannerExpoView, value: Boolean -> view.active = value }
      Prop("generation") { view: ScannerExpoView, value: Int -> view.generation = value }
      Prop("scanId") { view: ScannerExpoView, value: Int -> view.scanId = value }
      OnViewDidUpdateProps { view ->
        view.scanner.request(view.active, view.generation, view.scanId)
      }
      OnViewDestroys { view -> view.scanner.dispose() }
    }
  }
}

class ScannerExpoView(context: Context, appContext: AppContext) : ExpoView(context, appContext) {
  override val shouldUseAndroidLayout = true
  private val onWindowChanged by EventDispatcher()
  private val onBarcodeScanned by EventDispatcher()
  private val onMountError by EventDispatcher()
  var active = false
  var generation = -1
  var scanId = 0
  val scanner = ScannerCameraView(context)

  init {
    scanner.onWindowChanged = { allowed, generation ->
      onWindowChanged(mapOf("allowed" to allowed, "generation" to generation))
    }
    scanner.onBarcodeScanned = { data, generation, scanId ->
      onBarcodeScanned(mapOf("data" to data, "generation" to generation, "scanId" to scanId))
    }
    scanner.onError = { generation, scanId ->
      onMountError(mapOf("generation" to generation, "scanId" to scanId))
    }
    addView(scanner, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
  }
}
