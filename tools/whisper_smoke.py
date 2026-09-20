"""Real, opt-in model smoke test; supply a local speech audio path."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from faster_whisper import WhisperModel
from stt.media import decode

root = Path(__file__).resolve().parent.parent
model = WhisperModel("base", device="cpu", compute_type="int8", download_root=str(root / "data" / "models"))
assert all(language in model.supported_languages for language in ("bs", "hr", "sr"))
print("Model supports bs, hr, sr", flush=True)
source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "test-results" / "jfk.flac"
decode(source, root / "test-results" / "speech-smoke-normalized.wav")
for language in ("bs", "hr", "sr"):
    stream, info = model.transcribe(str(root / "test-results" / "speech-smoke-normalized.wav"), language=language, task="transcribe", word_timestamps=True, vad_filter=True)
    segments = list(stream)
    assert segments and all(s.end > s.start for s in segments)
    assert info.language == language
    print(f"{language}: {len(segments)} segments, word timestamps present: {bool(segments[0].words)}", flush=True)
