"""Prepare a pinned CPU model runtime and optionally serve it on loopback."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tarfile
from urllib.request import urlretrieve

ASSETS = {
    "llama.tar.gz": ("https://github.com/ggml-org/llama.cpp/releases/download/b12000/llama-b12000-bin-ubuntu-x64.tar.gz",
                     "c56588b49ed4be846b115188407ea2b601fa3a5c30b8c25ad60e8344dfc7a4fd"),
    "qwen.gguf": ("https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
                  "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"),
}


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected) in ASSETS.items():
        target = directory / filename
        if not target.exists():
            urlretrieve(url, target)
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected:
            raise ValueError("Pinned runtime/model checksum mismatch; no model will be launched")
    binary = directory / "llama-b12000/llama-server"
    if not binary.is_file():
        with tarfile.open(directory / "llama.tar.gz") as archive:
            archive.extractall(directory, filter="data")
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=18087)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a non-privileged port")
    directory = args.directory.resolve()
    binary = prepare(directory)
    print("Pinned CPU runtime/model verified", flush=True)
    if args.serve:
        subprocess.run([str(binary), "-m", str(directory / "qwen.gguf"), "--host", "127.0.0.1",
                        "--port", str(args.port), "--alias", "sapar-pm-qwen", "--threads", "4",
                        "--ctx-size", "2048", "--parallel", "1"], check=True)


if __name__ == "__main__":
    main()
