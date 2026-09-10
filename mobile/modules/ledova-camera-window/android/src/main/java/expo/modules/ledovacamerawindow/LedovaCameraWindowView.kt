package expo.modules.ledovacamerawindow

import android.content.Context
import android.view.View
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView

class LedovaCameraWindowView(context: Context, appContext: AppContext) : ExpoView(context, appContext) {
  private val onWindowChange by EventDispatcher()
  private var ownerId = ""
  private var generation = 0
  private var previousAllowed: Boolean? = null
  private var ownerChanged = false
  private var initialized = false
  private var attached = false
  private var retired = false

  init {
    initialized = true
  }

  fun setOwner(value: String) {
    if (ownerId == value) return
    ownerId = value
    ownerChanged = true
  }

  fun publishWindow() {
    if (!initialized || ownerId.isEmpty() || generation == Int.MAX_VALUE) return
    val isAttached = attached && isAttachedToWindow
    val visible = windowVisibility == VISIBLE
    val shown = isShown
    val focused = hasWindowFocus()
    val allowed = !retired && isAttached && visible && shown && focused && generation < Int.MAX_VALUE - 1
    if (!ownerChanged && allowed == previousAllowed) return
    ownerChanged = false
    previousAllowed = allowed
    generation += 1
    onWindowChange(mapOf(
      "ownerId" to ownerId,
      "generation" to generation,
      "allowed" to allowed,
      "attached" to isAttached,
      "windowVisible" to visible,
      "viewVisible" to shown,
      "focused" to focused
    ))
  }

  fun retire() {
    retired = true
    publishWindow()
  }

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    attached = true
    publishWindow()
  }

  override fun onDetachedFromWindow() {
    attached = false
    publishWindow()
    super.onDetachedFromWindow()
  }

  override fun onWindowFocusChanged(hasWindowFocus: Boolean) {
    super.onWindowFocusChanged(hasWindowFocus)
    publishWindow()
  }

  override fun onWindowVisibilityChanged(visibility: Int) {
    super.onWindowVisibilityChanged(visibility)
    publishWindow()
  }

  override fun onVisibilityChanged(changedView: View, visibility: Int) {
    super.onVisibilityChanged(changedView, visibility)
    publishWindow()
  }
}
