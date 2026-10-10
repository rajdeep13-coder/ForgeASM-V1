# Multimodal Copilot input

Photo input is capability-gated by `GET /api/copilot/capabilities`. When the
active model reports `supports_images: false`, the UI does not show an upload
control and displays the gateway's reason. No image support is simulated.

The browser decodes the selected file, scales its largest dimension to at most
1600 pixels, and re-encodes it as JPEG. Re-encoding removes EXIF metadata. The
resulting data URL is previewed with the label "Exactly the image sent" before
it is submitted.

The pipeline has two explicit stages:

1. Gemma returns a bounded JSON transcription containing pseudo-program text,
   test input, expected result, memory architecture, and cycle cap.
2. The user confirms or edits that JSON. Only then does the normal strict
   assembly agent run. Its deterministic checker uses the confirmed values,
   and the UI labels the result `user-confirmed values`.

Text inside the image is untrusted data. The transcription prompt explicitly
rejects requests to change the checker, expected values, or cycle cap.

Real handwritten-photo accuracy requires six user-provided photos and a
human-authored expected-spec CSV. This repository does not claim accuracy
numbers without those artifacts and a configured vision-capable Gemma model.
