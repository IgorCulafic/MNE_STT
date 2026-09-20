"""Decode once from the original; all playback and crops share its timeline."""
import io
import os
import shutil
import subprocess
import wave
import numpy as np
from .domain import Conflict


def ffmpeg_executable():
    configured = os.environ.get("FFMPEG_BINARY")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def decode(source, destination):
    ffmpeg = ffmpeg_executable()
    if ffmpeg:
        result = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(source),
                                 "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            reason = result.stderr[-1500:]
            raise Conflict("Media could not be decoded. Check that the file is readable and contains an audio track. " + reason)
    else:
        # A useful minimal installation still handles PCM WAV, including tests.
        try:
            with wave.open(str(source), "rb") as wav:
                if wav.getsampwidth() != 2 or wav.getnchannels() != 1 or wav.getframerate() != 16000:
                    raise Conflict("Install requirements.txt for FFmpeg decoding. Without it, use 16 kHz mono PCM16 WAV.")
                wav.readframes(wav.getnframes())
            shutil.copyfile(source, destination)
        except (wave.Error, EOFError):
            raise Conflict("Install requirements.txt to decode this media format. The file must contain readable audio.")
    with wave.open(str(destination), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
    if duration < 0.001:
        raise Conflict("The recording has no usable audio.")
    return duration


def peaks(path, count=1600):
    with wave.open(str(path), "rb") as wav:
        n = wav.getnframes()
        step = max(1, int(np.ceil(n / count)))
        result = []
        while data := wav.readframes(step):
            values = np.frombuffer(data, dtype="<i2").astype(np.float32)
            result.append(round(float(np.max(np.abs(values))) / 32768, 4))
    return result


def chunk(path, start, end):
    with wave.open(str(path), "rb") as src:
        rate = src.getframerate()
        first, last = round(start * rate), round(end * rate)
        if not 0 <= first < last <= src.getnframes():
            raise Conflict("Chunk boundaries fall outside the recording.")
        src.setpos(first)
        raw = src.readframes(last - first)
        out = io.BytesIO()
        with wave.open(out, "wb") as dst:
            dst.setparams(src.getparams())
            dst.writeframes(raw)
    return out.getvalue()
