import json
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    dex = [archive.read(name) for name in archive.namelist() if name.endswith(".dex")]
    if not dex:
        raise SystemExit("Camera artifact has no DEX files.")
    required = [
        b"Lexpo/modules/camera/ExpoCameraView;",
        b"Lexpo/modules/ledovacamerawindow/LedovaCameraWindowView;",
    ]
    for identity in required:
        if not any(identity in part for part in dex):
            raise SystemExit("Camera artifact has a missing native class descriptor.")
    for marker in (b"cameraWindowRevoked", b"hasCameraWindow"):
        if not any(marker in part for part in dex):
            raise SystemExit("Camera artifact does not contain the reviewed native guard.")
    for marker in (b"LedovaCameraWindowProbe", b"cameraProbeSnapshot"):
        if any(marker in part for part in dex):
            raise SystemExit("Ordinary camera artifact contains native test hooks.")
    print(
        json.dumps(
            {"camera_class_descriptors": len(required), "guard_markers": 2, "probe_markers": 0}
        )
    )
