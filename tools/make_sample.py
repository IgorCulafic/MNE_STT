"""Generate an explicitly synthetic recording for manual UI / timing QA."""
import json
import math
from pathlib import Path
import struct
import wave

root = Path(__file__).resolve().parent.parent / "test-results"
root.mkdir(exist_ok=True)
with wave.open(str(root / "timing-practice.wav"), "wb") as out:
    out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
    for second in range(30):
        out.writeframes(b"".join(struct.pack("<h", int(9000 * (.25 + .75 * abs(math.sin(i / 2300))) * math.sin((second * 16000 + i) * math.tau * (220 + second * 10) / 16000))) for i in range(16000)))
texts = [
    "[Synthetic tone · calibration only, no recorded speech.]",
    "Unicode editing sample: č, ć, đ, š, ž, ś, ź. Ћирилица остаје.",
    "Drag the boundary or shift this segment. Its neighbors stay synchronized.",
    "Listen to the original recording before and after the selected segment.",
    "Verify, flag, undo, and export the corrected timing.",
    "[End of synthetic timing exercise.]",
]
rows = [{"id": f"{i + 1:03d}", "text": t, "start": i * 5, "end": (i + 1) * 5} for i, t in enumerate(texts)]
(root / "timing-practice.json").write_text(json.dumps({"segments": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
print(root)
