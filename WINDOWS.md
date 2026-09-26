# Windows setup and launch

Download `MNE-STT-v1.1.0-windows.zip` from the [GitHub release](https://github.com/IgorCulafic/MNE_STT/releases/tag/v1.1.0). **Extract the entire ZIP** to a writable folder before running anything, and keep the files together. Windows x64 is the supported target.

| File | What it does |
| --- | --- |
| `install.bat` | Finds 64-bit Python 3.11-3.14, creates `.venv`, and installs the app, FFmpeg, and Whisper dependencies. If Python is missing, attempts a per-user Python 3.12 installation through winget. |
| `download-models.bat` | Downloads tiny, base, small, medium, large-v3, and large-v3-turbo: all six multilingual models offered by the app. |
| `install-and-download-all.bat` | Runs installation followed by all model downloads. |
| `run.bat` | Starts the app at http://127.0.0.1:8769 and opens your browser when ready. If the app is already running, opens that instance. |

For everything in one setup, double-click **install-and-download-all.bat**, then **run.bat**. Keep the server console open while using the app; Ctrl+C stops it.

Initial setup requires internet access and several GB of storage and download data for the model weights. Allow extra disk space for recordings and decoded audio. Downloads run sequentially, retry transient failures, and reuse cached files when rerun. They do not load all models into RAM. Failed operations remain visible in the console and return a nonzero exit code.

The ZIP includes the audio-only Dijaspora recording and original Gemini transcript in `examples/dijaspora/`. You can review that timestamped example after installation without downloading any models. Model weights are fetched from the repositories selected by faster-whisper and are not embedded in the ZIP. This is a batch-based Windows package, not a standalone EXE.

## Options

Run these from a command prompt in the extracted folder:

```bat
download-models.bat --list
download-models.bat --models base
download-models.bat --models small medium
download-models.bat --models base --local-only
run.bat --no-browser
```

`--local-only` checks already downloaded files without contacting the network. `--no-browser` starts the server without opening a browser. For scripted use, set `STT_NO_PAUSE=1` to suppress pauses in the individual batch files; the combined setup always pauses at the end.

Models go in `data/models/` by default. Set `STT_MODEL_CACHE` to change the model folder. `STT_DATA_DIR` changes the project directory and its default model folder. Set overrides in the environment before starting either the downloader or app; both use the same cache rules.

## Troubleshooting

- If automatic Python installation is unavailable, install **64-bit Python 3.12** from [python.org](https://www.python.org/downloads/windows/), include the Python launcher, and rerun `install.bat`. Automatic installation needs Windows App Installer / winget.
- Extract to a user-writable folder. Administrator rights are normally unnecessary. The installer uses a process-only PowerShell execution-policy override; it does not change system policy.
- An unusable existing `.venv` is reported for manual repair. Rename that folder and rerun the installer. Do not delete `data/`: it contains your projects and cached models.
- A download failure can be retried by rerunning the downloader. Existing cached files are reused. The console lists failed model names.
- A busy port belonging to another service produces an error instead of starting a second server. Close that service before retrying.
- Larger models need more RAM and run more slowly on CPU. Downloading a model does not select it automatically; choose the desired model on Import.

## Release verification

The release includes a SHA-256 checksum for the ZIP and `BUILD.json` inside it with the source commit. Compare the checksum using PowerShell:

```powershell
Get-FileHash .\MNE-STT-v1.1.0-windows.zip -Algorithm SHA256
Get-Content .\MNE-STT-v1.1.0-windows.zip.sha256
```

Maintainers can regenerate a package from committed source with `python tools/build_release.py v1.1.0`. The builder includes only committed files, sets Windows line endings for launch scripts, and excludes local runtime directories.
