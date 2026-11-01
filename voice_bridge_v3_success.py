import json
import queue
import time
from pathlib import Path

import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

FOLDER = Path.home() / "so101_voice"
MODEL_PATH = FOLDER / "vosk-model-small-ja-0.22"
OUTPUT = FOLDER / "voice_command.json"
LOG_FILE = FOLDER / "recognition_log_v3.jsonl"

SAMPLE_RATE = 16000

model = Model(str(MODEL_PATH))

# 認識候補を限定しない通常の音声認識
recognizer = KaldiRecognizer(model, SAMPLE_RATE)
recognizer.SetWords(True)

audio_queue = queue.Queue(maxsize=30)


def callback(indata, frames, time_info, status):
    if status:
        print("マイク警告:", status, flush=True)

    try:
        audio_queue.put_nowait(bytes(indata))
    except queue.Full:
        print("音声バッファ満杯", flush=True)


def save_result(spoken, raw_result):
    payload = {
        "text": spoken,
        "timestamp": time.time()
    }

    tmp = FOLDER / "voice_command.tmp"
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8"
    )
    tmp.replace(OUTPUT)

    log = {
        **payload,
        "vosk_raw": raw_result
    }

    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")


print("=== SO-101 音声認識 v3 ===")
print("自由発話モード：認識候補の制限なし")
print("終了は Ctrl+C")

try:
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=4000,
        dtype="int16",
        channels=1,
        callback=callback
    ):
        while True:
            audio = audio_queue.get()

            if not recognizer.AcceptWaveform(audio):
                continue

            result = json.loads(recognizer.Result())
            raw_text = result.get("text", "").strip()

            if not raw_text:
                continue

            print("\nVosk書き起こし:", raw_text, flush=True)

            # WSL側の既存プログラムと互換性を維持
            spoken = raw_text.replace(" ", "").replace("　", "")

            save_result(spoken, result)

except KeyboardInterrupt:
    print("\n音声認識を終了しました")
