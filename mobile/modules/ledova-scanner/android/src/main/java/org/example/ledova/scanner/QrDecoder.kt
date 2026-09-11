package org.example.ledova.scanner

import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.Executor

internal class QrDecoder(
  private val executor: Executor,
  private val current: () -> Boolean,
  private val onBarcode: (String) -> Unit,
  private val onError: () -> Unit
) {
  private var closed = false
  private val scanner = BarcodeScanning.getClient(
    BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
  )

  fun read(image: InputImage, release: () -> Unit) {
    if (closed || !current()) {
      release()
      return
    }
    try {
      scanner.process(image)
        .addOnSuccessListener(executor) { barcodes ->
          if (!closed && current()) {
            val data = barcodes.firstOrNull()?.rawValue
            if (data != null) onBarcode(data)
          }
        }
        .addOnFailureListener(executor) { if (!closed && current()) onError() }
        .addOnCompleteListener(executor) { release() }
    } catch (_: Exception) {
      release()
      if (!closed && current()) onError()
    }
  }

  fun close() {
    closed = true
    scanner.close()
  }
}
