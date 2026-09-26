# Montenegrin STT Review

A local, single-user research workspace for reviewing speech transcripts and correcting their timestamps. The interface follows the supplied import/review references: blue navigation, a segment list, text editor, context waveform, timing controls, progress, and history.

## Included recording and transcript

The [Dijaspora example](examples/dijaspora/README.md) includes a lossless audio-only copy of the recording and the original Gemini transcript. After starting the app, import `examples/dijaspora/dijaspora-u-fokusu.flac` with `examples/dijaspora/gemini-transcript.txt`, keeping **Default** chunking. This loads 117 cues without requiring Whisper. Twelve zero-length timestamps are flagged for manual repair. See the example README for provenance and checksums.

The repository contains source code, tests, dependency lists, startup scripts, and this example. Virtual environments, model downloads, local projects/databases, and temporary test output are excluded; the app creates its runtime folders as needed.

## Install and run

**Windows quick start:** download and fully extract the ZIP from the [v1.1.0 release](https://github.com/IgorCulafic/MNE_STT/releases/tag/v1.1.0). Double-click **`install-and-download-all.bat`**, then **`run.bat`**. Separate `install.bat` and `download-models.bat` files are also included. See [WINDOWS.md](WINDOWS.md) for requirements, download options, and troubleshooting.

Python **3.11 or 3.12 is recommended**, especially for Whisper's native dependencies. The complete app, including Whisper, was also verified with Python 3.14.5 and the bundled dependencies. No Node.js build is needed.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:8769**. Stop with Ctrl+C. On macOS/Linux, activate with `source .venv/bin/activate`. The server binds to localhost and rejects cross-origin writes. Do not expose this single-user application to a public network.

For media-only transcription or alignment of untimed text:

```powershell
python -m pip install -r requirements-whisper.txt
```

Restart after installing. A multilingual faster-whisper model runs locally on CPU with int8 compute. Select `tiny`, `base`, `small`, `medium`, `large-v3`, or `large-v3-turbo` before importing. First use downloads weights from Hugging Face (from roughly 75 MB to several GB depending on the model); later runs reuse `data/models/` (override with `STT_MODEL_CACHE`). Model weights are not included in the repository. Larger models require substantially more memory and time. Bosnian (`bs`), Croatian (`hr`), and Serbian (`sr`) are passed directly with `task="transcribe"`. The loaded model's supported-language list is checked before inference; unsupported settings produce an error rather than a substitution.

The bundled `imageio-ffmpeg` dependency supplies FFmpeg on supported platforms. A system `ffmpeg` or the `FFMPEG_BINARY` environment variable can override it. Without FFmpeg, only 16 kHz mono PCM16 WAV is supported. Settings reports decoder/Whisper availability. All actual files are decoded, not trusted by extension. A video without an audio track fails with an actionable error.

## Workflows

1. **Transcript and media:** import TXT, SRT, VTT or JSON alongside your recording. Timestamped text is preserved; no transcription model is run. Invalid timestamps/overlaps remain visible and flagged, and export is blocked until repaired.
2. **Media only:** select the spoken language and model. Whisper generates a timestamped transcript for review.
3. **Untimed transcript:** existing text is matched to Whisper word timestamps using monotonic exact token anchors. Missing anchors are interpolated. This is assistive alignment, **not phonetic forced alignment**. All aligned segments are flagged for listening/manual correction, coverage is shown, and original text is never rewritten. If speech recognition itself fails, import reports failure and preserves the original files.

Supported media containers/codecs depend on the FFmpeg build: common WAV, MP3, M4A, AAC, FLAC, OGG, OPUS, MP4, MOV, MKV, WEBM, and AVI are accepted when decodable. The first audio track is used. Video images are not displayed; the full audio track is available for review.

## Transcript conventions

Files must be UTF-8 (a BOM is accepted). SRT and WebVTT support multiline cues; VTT header metadata, cue IDs, cue positioning settings, and NOTE/STYLE/REGION blocks are accepted where relevant but are not reproduced in exports. Cue text, including markup, is preserved as literal text. Timestamped TXT supports Gemini-style `[HH:MM:SS - HH:MM:SS]` headers, multiline cue text, and a final `end` marker. These cues use the supplied times without running Whisper; invalid timings are retained for repair. An empty trailing `end` marker is ignored. Plain TXT without timestamp headers uses one nonempty line per segment; spaces within each line and Unicode are retained. Blank lines are separators, not segments.

JSON accepts a top-level array or this object. Times are numeric seconds on the recording's audio timeline. IDs are stable and unique, with 1–80 letters, digits, underscores or hyphens. If omitted, IDs are assigned in source order. Leave out both times on every segment to request alignment. Mixed timed/untimed JSON is rejected. Imported review statuses are reset to unreviewed because this is a new research project.

```json
{
  "segments": [
    {"id": "001", "start": 0.0, "end": 4.2, "text": "Śutra ćemo razgovarati."},
    {"id": "002", "start": 4.2, "end": 8.0, "text": "Čujem đecu. Ћирилица остаје."}
  ]
}
```

All text stays Unicode, including č, ć, đ, š, ž, ś, ź and Cyrillic. No regional normalization, translation, or script conversion is applied to supplied text. Whisper's generated spelling is model output and must be reviewed.

## Reviewing and timing

Use **✓ Correct** to approve a segment or **✕ Incorrect** to mark it for later correction. The transcript remains editable and autosaves. An incorrect segment requires a real text change before approval; timing edits, whitespace-only edits, and changing status do not satisfy this requirement. It stays incorrect after editing until you explicitly approve it. Use the **Incorrect** filter to return to outstanding corrections. Undo restores both text and the correction requirement. Correct and approve an incorrect segment before splitting or merging it. Automated timing flags are separate and do not count as reviewed. Reverting to the rejected text makes the correction required again.

- Select a segment to play it; selection starts audio when allowed by browser playback policy.
- Click the waveform to seek without editing boundaries. Drag the two blue handles to edit start/end, or enter `HH:MM:SS.mmm` and use ±0.1/±1 second buttons. Shift buttons move both endpoints together.
- The waveform defaults to 10 seconds of original audio on each side, clamped at recording edges. Choose 20 seconds or the full recording. The lower slider always seeks throughout the original recording. Seeking outside the segment enables unrestricted context playback; reselect the segment to restore segment looping.
- Shared boundaries update together. Existing gaps are preserved until the edited boundary crosses a neighbor. Only adjacent affected endpoints change. An edit consuming a neighbor, causing an overlap, or leaving recording bounds is rejected in full.
- Changed verified segments return to unreviewed. Automatically adjusted neighbors are highlighted in amber. A modified marker is separate from review status.
- Compare shows the original post-processing snapshot alongside the working version. The raw imported transcript is also retained on disk.

Shortcuts: Space plays/pauses outside fields; Alt+Left/Right navigates; Ctrl/Cmd+Enter verifies and advances; Ctrl/Cmd+Shift+F marks incorrect; Ctrl/Cmd+S saves; Ctrl/Cmd+Z and Shift+Z undo/redo outside fields. Focus a boundary handle and use arrow keys for 0.1-second edits, or Shift+arrow for 1 second. Text fields retain native text undo.

## Persistence and research records

SQLite stores authoritative segments, monotonically increasing revisions, undo/redo history, and audit entries in one transaction. Text autosaves after 650 ms; timing/status changes save immediately. Every change includes timestamps, project/revision, affected IDs, and old/new values. Direct and propagated edits are distinct. History also records processing settings, failures, and export requests/completion. Optimistic revision checks reject edits from stale tabs. Use one editing tab per project; refresh after a stale-revision error. Unsent text drafts are retained in browser local storage and restored with a visible Save prompt.

`data/` contains `projects.sqlite3`, its WAL files while running, background job records, and one folder per project. Originals are stored as `original-media` and `original-transcript` with their filenames in `original-files.json`; they are never overwritten. Other immutable source snapshots include parsed input, model output (if used), and initial processed segments. `audio.wav` is decoded once from the original into 16 kHz mono PCM16; playback, alignment and all chunks use that same timeline. `STT_DATA_DIR` selects another data directory. Back up the **entire** directory with the server stopped. Reopen saved projects from the Import screen.

Processing and ZIP export run in background workers. Pollable job status is persisted; interrupted jobs are marked failed on restart. Retry import after an interruption. Failed imports keep originals and failure logs in the data directory. Completed projects and edits survive restart. Undo/redo is persisted without a history limit, so large annotation projects may grow in size.

## Export

Download TXT, SRT, VTT, structured JSON, a segment manifest, audit JSON, a selected WAV chunk, or one ZIP bundle. All export inputs are captured from one saved revision. Editing during ZIP generation cannot change that snapshot. Every chunk is freshly cropped from `audio.wav`, never from a prior chunk. Sample boundaries are rounded to the nearest 16 kHz sample; committed timestamps use milliseconds (16 samples/ms). No surrounding context is included. The ZIP contains:

```text
transcript.txt / .srt / .vtt / .json
manifest.json
audit.json
progress.json
original-transcript.json
audio/<stable-id>.wav
```

The audit snapshot in a ZIP includes its export request; completion is appended to the live project log after the file is successfully written. Original media is kept in the project folder rather than duplicated into the ZIP. WAV export is deliberately normalized to mono 16 kHz for research/STT; it is not a lossless copy of original sample rate or channel layout.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover shared boundaries, forward/backward shifts, gaps, overlap prevention, recording bounds, rejected edits, neighboring review invalidation, undo/redo, stale revisions, save/reload, Unicode, parsers, alignment flags, and export snapshots. The integration test imports a real generated PCM recording and SRT, edits timing, exports while another edit occurs, and checks each WAV's sample count **and exact sample bytes** against the authoritative recording. Speech-workflow contract tests use a controlled backend; running a real model additionally requires the Whisper dependency and downloaded weights.

## Project layout and limits

`stt/domain.py` owns boundary rules; `store.py` owns transactions/history; `transcripts.py` handles text; `media.py` handles decoding/cropping; `speech.py` handles model inference/alignment; `exports.py` packages snapshots; `app.py` exposes the local API; `web/` is the dependency-free browser UI.

The design targets desktop, single-user work. There is no authentication, collaboration, automatic speaker identification or automatic dialect correction. Assisted alignment can be inaccurate for heavily differing text, repeated phrases, or scripts that differ from recognition output; manual review is required. Very long recordings require disk space for originals, normalized PCM, and exports. Inference cannot currently be cancelled inside the model call. Standard WAV's size limit also applies to exceptionally long recordings. The UI reports invalid imports rather than silently repairing them. The built-in API documentation is available at `/docs`.

Backend references: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [Whisper language tokens](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py).

## Verification performed

77 automated tests pass. Additional real-model smoke tests exercised `bs`, `hr`, and `sr` with word timestamps, and the full import API for media-only transcription and text-preserving alignment. The speech smoke fixture was the upstream faster-whisper `tests/data/jfk.flac` recording; this verifies execution, not Montenegrin transcription quality. Browser checks covered Unicode editing, saving, neighbor propagation, and undo. Run `python tools/make_sample.py` to generate an explicitly labelled synthetic timing fixture for manual testing.


## Chunking modes

Choose a chunking mode when importing, or use **Review → Chunking → Auto chunk…** on an existing project. In Review, choose the selected segment or the whole transcript, inspect the preview, then apply. Default leaves existing transcript/Whisper cues as they are; it does not discard edits or reset a project.

- **Default:** keep the supplied cues or model-generated segments. This remains the default on import.
- **Target duration:** split long cues around a configurable target (10 seconds initially; 1–600 seconds supported). When available, word timestamps move the cut to the nearest word boundary. Targets are approximate: a cue with too few words may stay longer than the target.
- **Sentence endings:** split on sentence-final punctuation, accounting for common abbreviations and decimal numbers. Word timestamps determine audio boundaries when available. Otherwise, time is interpolated within the cue and all affected chunks are flagged for manual timing review.
- **Speech pauses / end of speech:** split at interior silence lasting at least the configured minimum (0.6 seconds initially; 0.2–5 seconds supported). The original normalized recording is scanned in 20 ms frames at a -35 dBFS RMS threshold. Leading/trailing silence does not create extra chunks. This is pause detection, not speaker identification; noise or low-volume speech may require manual correction.
- **Sentence endings or speech pauses:** use both sets of boundaries.

Automatic chunking preserves existing cue endpoints and gaps. It splits within each cue, without merging across cues or rewriting supplied text. Known word timing is used only while it still matches the working text and boundaries; text/timing edits invalidate those mappings. With no reliable mapping, assignment of text to pause/duration chunks is provisional and flagged. Newly generated Whisper projects retain word-level timing for this purpose; older projects still work with explicitly marked estimates.

**Manual splitting:** select a segment, seek to the desired audio point, then click **Split…**. Enter the split time and click between words in the read-only text to choose the text break (or enter its character position). The preview shows both pieces. You can mark a manual boundary as a speaker turn without running a speaker-identification model. Times must be inside the segment and both text portions must be nonempty.

**Manual merging:** click **Merge next…** to combine the selected cue with its immediate successor. The preview explicitly warns if the resulting audio includes an existing gap. Text is preserved with a newline between the two original portions.

Chunking is one atomic, revision-checked, undoable change. A split retains the first chunk's ID and assigns unique stable IDs to its new siblings. A merge retains the first ID; removed IDs remain in history. `source_ids` links descendants to their original cues, so Compare continues to work after structural changes. Original snapshots and raw uploads remain unchanged. Undo/redo restores the exact IDs, text, timing, review statuses and chunking settings. Plans become invalid if the project is edited after the preview; generate another preview in that case. Exports use the resulting authoritative chunk list, and manifests include chunking settings and source lineage.

The chunking tests include real PCM silence detection, sentence/duration planning, malformed requests, manual Unicode splits, merge gaps, source lineage, added/deleted audit records, undo/redo across changing segment counts, stale previews, import options and matching ZIP audio durations.
