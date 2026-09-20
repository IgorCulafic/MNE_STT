# First review recording

This folder contains the real recording and Gemini transcript used for the first review session.

- `dijaspora-u-fokusu.flac`: complete audio-only recording, 33 minutes 36.049375 seconds. Lossless FLAC, mono, 16 kHz, 16-bit. Its decoded samples are identical to the review application's normalized audio from the supplied MP4.
- `gemini-transcript.txt`: the original Gemini transcript, copied byte-for-byte. Includes speaker labels and 117 timestamped cues.
- `source.json`: original filename, audio properties, checksums, and known timing issue IDs.

## Try it

1. Install and run the app using the main README.
2. On **Import**, select `gemini-transcript.txt` as the transcript and `dijaspora-u-fokusu.flac` as the audio.
3. Leave chunking on **Default** and continue to Review. The existing timestamps are used directly; Whisper and model downloads are unnecessary for this example.
4. Review the text with **Correct** / **Incorrect** and make corrections in the editor. Filter by **Flagged** to find the 12 zero-length timestamps that require manual repair before chunking or export.

The transcript is an unverified model output. Wording and timestamps have deliberately been preserved for testing, not silently corrected. The empty `[00:32:48 - end]` closing marker contains no transcript text and does not create a segment.

The original video and local database are not needed to reproduce this import. New imports create a fresh project in `data/`.

The media and transcript were supplied by the repository owner for this review workflow. No redistribution license is granted for the source recording or transcript.
