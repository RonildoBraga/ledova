package org.example.ledova.scanner

import android.graphics.BitmapFactory
import androidx.core.content.ContextCompat
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.mlkit.vision.common.InputImage
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class QrDecoderTest {
  private val instrumentation = InstrumentationRegistry.getInstrumentation()
  private val executor = ContextCompat.getMainExecutor(instrumentation.context)

  private fun image(): InputImage {
    val bitmap = instrumentation.context.assets.open("synthetic-wallet-qr.png").use { BitmapFactory.decodeStream(it) }
    return InputImage.fromBitmap(bitmap, 0)
  }

  @Test fun decodesARealQrImageAndReleasesItsFrame() {
    val complete = CountDownLatch(1)
    val results = mutableListOf<String>()
    var failures = 0
    lateinit var decoder: QrDecoder
    instrumentation.runOnMainSync {
      decoder = QrDecoder(executor, { true }, { results.add(it) }, { failures += 1 })
      decoder.read(image()) { complete.countDown() }
    }
    assertTrue("decoder did not finish", complete.await(15, TimeUnit.SECONDS))
    instrumentation.runOnMainSync { decoder.close() }
    assertEquals(listOf("ledova-synthetic-wallet-qr"), results)
    assertEquals(0, failures)
  }

  @Test fun lateRealDecoderResultIsRefusedButTheFrameIsStillReleased() {
    val complete = CountDownLatch(1)
    val control = CountDownLatch(1)
    val results = mutableListOf<String>()
    var current = true
    lateinit var decoder: QrDecoder
    instrumentation.runOnMainSync {
      decoder = QrDecoder(executor, { current }, { results.add(it) }, { fail("decoder error") })
      decoder.read(image()) { complete.countDown() }
      current = false
    }
    assertTrue("retired frame was not released", complete.await(15, TimeUnit.SECONDS))
    assertTrue(results.isEmpty())
    instrumentation.runOnMainSync {
      current = true
      decoder.read(image()) { control.countDown() }
    }
    assertTrue("positive control did not finish", control.await(15, TimeUnit.SECONDS))
    instrumentation.runOnMainSync { decoder.close() }
    assertEquals(listOf("ledova-synthetic-wallet-qr"), results)
  }
}
