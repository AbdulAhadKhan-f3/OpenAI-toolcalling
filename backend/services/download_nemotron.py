"""Download the Nemotron Parakeet TDT 0.6B (INT8) model files for sherpa-onnx.

Usage:
    cd backend
    python -m services.download_nemotron

Downloads from HuggingFace into  models/nemotron-asr/
"""
import os
import sys
import tarfile
import urllib.request
import shutil
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "nemotron-asr"

# The HuggingFace repo published by csukuangfj (sherpa-onnx maintainer)
HF_REPO = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2"
BASE_URL = f"https://huggingface.co/{HF_REPO}/resolve/main"

# Files we need
NEEDED = [
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "joiner.int8.onnx",
    "tokens.txt",
]


def download_file(url: str, dest: Path):
    """Download a single file with progress."""
    print(f"  Downloading {dest.name} ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ClinScribe/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  {dest.name}: {downloaded // (1024*1024)} MB / {total // (1024*1024)} MB ({pct}%)", end="", flush=True)
            print()  # newline after progress
    except Exception as e:
        if dest.exists():
            dest.unlink()
        raise RuntimeError(f"Failed to download {url}: {e}") from e


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    already = [f for f in NEEDED if (MODEL_DIR / f).exists()]
    if len(already) == len(NEEDED):
        print(f"All model files already present in {MODEL_DIR}")
        print("Delete the directory and re-run to force re-download.")
        return

    print(f"Downloading Nemotron Parakeet TDT 0.6B (INT8) to {MODEL_DIR}")
    print(f"Source: {HF_REPO}\n")

    for filename in NEEDED:
        dest = MODEL_DIR / filename
        if dest.exists():
            print(f"  {filename} — already exists, skipping")
            continue
        url = f"{BASE_URL}/{filename}"
        download_file(url, dest)

    # Verify all files are present
    missing = [f for f in NEEDED if not (MODEL_DIR / f).exists()]
    if missing:
        print(f"\nERROR: Still missing files: {', '.join(missing)}")
        sys.exit(1)

    print(f"\n✓ All model files downloaded to {MODEL_DIR}")
    print("You can now start the backend server.")


if __name__ == "__main__":
    main()
