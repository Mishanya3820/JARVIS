from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from jarvis_paths import RESOURCES_DIR

GIGAAM_DIR = Path(RESOURCES_DIR) / "gigaam_v3"

# Quantized GigaAM v3 E2E RNNT exported for sherpa-onnx.
# The model weights are intentionally downloaded at runtime and are NOT stored in Git.
MODEL_FILES = {
    "gigaam_v3_e2e_rnnt_encoder_int8.onnx": {
        "url": "https://huggingface.co/pantinor/gigaam-v3/resolve/main/gigaam_v3_e2e_rnnt_encoder_int8.onnx",
        "sha256": "2cac62d0c270bd128f898f2be1a2d34780d524a6e9483888ebac7b00f97410f1",
    },
    "decoder.onnx": {
        "url": "https://huggingface.co/pantinor/gigaam-v3/resolve/main/gigaam_v3_e2e_rnnt_decoder.onnx",
        "sha256": "781971998e6a355d6a714f6932a30eab295e7ba0d14fd7e0f78c83b87e811860",
    },
    "joiner.onnx": {
        "url": "https://huggingface.co/pantinor/gigaam-v3/resolve/main/gigaam_v3_e2e_rnnt_joint.onnx",
        "sha256": "602ff7017a93311aad34df1437c8d7f49911353c13d6eae7a6ee7b041339465c",
    },
    "tokens.txt": {
        "url": "https://huggingface.co/pantinor/gigaam-v3/resolve/main/gigaam_v3_e2e_rnnt_tokens.txt",
        "sha256": "7ddf22514c42c531358182c81446a8159771e9921019f09ae743ea622d40221d",
    },
}


def model_files_present() -> bool:
    return all((GIGAAM_DIR / name).is_file() for name in MODEL_FILES)


def runtime_available() -> bool:
    if not model_files_present():
        return False
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path, expected_sha256: str, progress_callback=None) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "JARVIS-GigaAM-installer/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(destination.name, downloaded, total)
    actual = _sha256(temporary)
    if actual.lower() != expected_sha256.lower():
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"Проверка GigaAM не пройдена для {destination.name}: "
            f"SHA-256 {actual} вместо {expected_sha256}"
        )
    os.replace(temporary, destination)


def install_gigaam(progress_callback=None) -> None:
    """Installs sherpa-onnx and downloads the external GigaAM v3 model."""
    GIGAAM_DIR.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback("pip", 0, 0)

    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "sherpa-onnx"],
            check=True,
        )

    for name, info in MODEL_FILES.items():
        destination = GIGAAM_DIR / name
        if destination.is_file() and _sha256(destination).lower() == info["sha256"].lower():
            if progress_callback:
                progress_callback(name, 1, 1)
            continue
        _download(info["url"], destination, info["sha256"], progress_callback)

    if not runtime_available():
        raise RuntimeError("GigaAM установлен не полностью: не найден sherpa-onnx или файлы модели.")
