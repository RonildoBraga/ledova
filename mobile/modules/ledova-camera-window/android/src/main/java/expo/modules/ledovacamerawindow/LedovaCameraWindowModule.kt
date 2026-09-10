package expo.modules.ledovacamerawindow

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class LedovaCameraWindowModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("LedovaCameraWindow")
    View(LedovaCameraWindowView::class) {
      Events("onWindowChange")
      Prop("ownerId") { view: LedovaCameraWindowView, ownerId: String ->
        view.setOwner(ownerId)
      }
      OnViewDidUpdateProps { view -> view.publishWindow() }
      OnViewDestroys { view -> view.retire() }
    }
  }
}
