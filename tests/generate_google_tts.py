#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "google-cloud-texttospeech",
#     "fire",
# ]
# ///

from google.cloud import texttospeech

# pip install google-cloud-texttospeech google-auth
# from google.oauth2 import service_account
# creds = service_account.Credentials.from_service_account_file("service-account.json", scopes=["https://www.googleapis.com/auth/cloud-platform"])
# client = texttospeech.TextToSpeechClient(credentials=creds)
# OR GOOGLE_APPLICATION_CREDENTIALS=/full/path/service-account.json
client = texttospeech.TextToSpeechClient()

def generate(text, out=None, voice="en-US-Studio-Q", lang="en-US", format="wav", play=False):
    audio_encodings = {
        "wav": texttospeech.AudioEncoding.LINEAR16,
        "mp3": texttospeech.AudioEncoding.MP3,
    }
    assert format in audio_encodings, f"Unsupported format: {format}. Supported formats: {list(audio_encodings.keys())}"
    if out is None:
        out = f"{text.replace(' ', '_')}.{format}"
    out = str(out)
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(language_code=lang, name=voice),
        audio_config=texttospeech.AudioConfig(audio_encoding=audio_encodings[format], sample_rate_hertz=16000)
    )
    with open(out, "wb") as f:
        f.write(response.audio_content)
    if play:
        import winsound
        winsound.PlaySound(out, winsound.SND_FILENAME)

def list_voices():
    for v in client.list_voices().voices:
        print(v.name, "-", v.language_codes)

if __name__ == "__main__":
    import fire
    fire.Fire(generate)
