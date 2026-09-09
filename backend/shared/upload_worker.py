import io
import json
import math
import resource
import sys
import warnings


class InvalidContent(Exception):
    pass


def check_dimensions(width, height, limits):
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise InvalidContent()
    pixels = math.ceil(width) * math.ceil(height)
    if pixels > limits["pixels"] or pixels * 4 > limits["decoded_bytes"]:
        raise InvalidContent()


def process_pdf(raw, limits, render):
    import pymupdf

    with pymupdf.open(stream=raw, filetype="pdf") as document:
        if document.needs_pass or document.is_repaired or not 1 <= document.page_count <= limits["pages"]:
            raise InvalidContent()
        for page in document:
            check_dimensions(page.rect.width * 2, page.rect.height * 2, limits)
            seen = set()
            decoded = 0
            for image in page.get_images(full=True):
                xref, _, width, height = image[:4]
                check_dimensions(width, height, limits)
                if xref not in seen:
                    decoded += width * height * 4
                    seen.add(xref)
                if decoded > limits["decoded_bytes"]:
                    raise InvalidContent()
        if not render:
            return "application/pdf"
        page = document[0]
        scale = min(2, limits["side"] / max(page.rect.width, page.rect.height))
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False, annots=False
        )
        if max(pixmap.width, pixmap.height) > limits["side"]:
            raise InvalidContent()
        return pixmap.tobytes("png")


def process_image(raw, limits, render):
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = limits["pixels"]
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(io.BytesIO(raw), formats=("PNG", "JPEG")) as image:
        check_dimensions(*image.size, limits)
        if getattr(image, "n_frames", 1) != 1:
            raise InvalidContent()
        mime = Image.MIME[image.format]
        image.verify()
    with Image.open(io.BytesIO(raw), formats=("PNG", "JPEG")) as image:
        image.load()
        if not render:
            return mime
        with image.convert("RGB") as converted:
            converted.thumbnail((limits["side"], limits["side"]), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()


def main():
    mode = sys.argv[1]
    limits = json.loads(sys.argv[2])
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory_bytes"], limits["memory_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_seconds"], limits["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["output_bytes"], limits["output_bytes"]))
    raw = sys.stdin.buffer.read(limits["input_bytes"] + 1)
    if not raw or len(raw) > limits["input_bytes"]:
        return 2
    try:
        if raw.startswith(b"%PDF-"):
            value = process_pdf(raw, limits, mode == "render")
        elif raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
            value = process_image(raw, limits, mode == "render")
        else:
            return 2
        if mode == "render":
            if len(value) > limits["output_bytes"]:
                return 2
            sys.stdout.buffer.write(value)
        else:
            print(json.dumps({"mime_type": value}))
        return 0
    except MemoryError:
        return 3
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main())
