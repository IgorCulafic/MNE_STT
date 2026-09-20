import subprocess
import wave
import pytest
from stt.domain import Conflict
from stt.media import decode, ffmpeg_executable


@pytest.mark.parametrize("suffix,codec", [("mp3", "libmp3lame"), ("flac", "flac"), ("m4a", "aac"), ("mp4", "aac")])
def test_decode_actual_encoded_media(tmp_path, suffix, codec):
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        pytest.skip("Install imageio-ffmpeg for encoded-media tests")
    source = tmp_path / ("source." + suffix)
    command = [ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=1"]
    if suffix == "mp4":
        command += ["-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-c:v", "libx264"]
    subprocess.run(command + ["-c:a", codec, str(source)], check=True, capture_output=True)
    output = tmp_path / "decoded.wav"
    duration = decode(source, output)
    assert 0.95 <= duration <= 1.1
    with wave.open(str(output), "rb") as wav:
        assert (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) == (1, 16000, 2)


def test_video_without_audio(tmp_path):
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        pytest.skip("Install imageio-ffmpeg for video tests")
    source = tmp_path / "silent.mp4"
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-c:v", "libx264", str(source)], check=True, capture_output=True)
    with pytest.raises(Conflict, match="audio track"):
        decode(source, tmp_path / "out.wav")
