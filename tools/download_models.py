"""Download all supported multilingual models without loading them into RAM."""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stt.models import MODELS, model_cache


def download_models(names, cache, local_only=False, download=None, sleep=time.sleep):
    if download is None:
        from faster_whisper.utils import download_model
        download = download_model
    cache.mkdir(parents=True, exist_ok=True)
    failures = []
    for index, name in enumerate(names, 1):
        print(f"[{index}/{len(names)}] {name}: checking cache / downloading...", flush=True)
        for attempt in range(1, (1 if local_only else 3) + 1):
            try:
                path = Path(download(name, cache_dir=str(cache), local_files_only=local_only))
                for filename in ("model.bin", "config.json", "tokenizer.json"):
                    file = path / filename
                    if not file.is_file() or not file.stat().st_size:
                        raise RuntimeError(f"Incomplete model: missing {filename}")
                print(f"  Ready: {path}", flush=True)
                break
            except Exception as exc:
                print(f"  Attempt {attempt}: {exc}", flush=True)
                if local_only or attempt == 3:
                    failures.append(name)
                else:
                    sleep(2 * attempt)
    if failures:
        print("Not ready: " + ", ".join(failures) + ". Rerun to retry; cached files are reused.")
        return 1
    print("All requested models are ready. You can now run run.bat.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--list", action="store_true", help="List supported models without downloading")
    parser.add_argument("--local-only", action="store_true", help="Check existing downloads without network access")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(MODELS))
        return 0
    print(f"Model cache: {model_cache()}")
    if not args.local_only:
        print("The full set of six models uses several GB of storage and internet data. Large models can take a while.", flush=True)
    try:
        return download_models(list(dict.fromkeys(args.models)), model_cache(), args.local_only)
    except ImportError:
        print("Whisper dependencies are missing. Run install.bat first.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDownload interrupted. Rerun to reuse completed downloads.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
