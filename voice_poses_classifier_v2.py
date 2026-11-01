import json
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

ALLOWED = {
    "起動": "work",
    "作業基準位置に行け": "work",
    "作業位置に移動": "work",
    "作業位置に行って": "work",
    "格納": "storage",
    "格納して": "storage",
    "格納位置に戻って": "storage",
    "あげて": "up",
    "さげて": "down",
    "うえ": "up",
    "した": "down",
    "まえ": "front",
    "うしろ": "back",
    "ひらいて": "open",
    "とじて": "close",
    "みぎ": "right",
    "ひだり": "left",
    "開いて": "open",
    "少し開いて": "open",
    "閉じて": "close",
    "掴んで": "close",
    "右": "right",
    "右へ": "right",
    "左": "left",
    "左へ": "left",
    "上げて": "up",
    "上": "up",
    "下げて": "down",
    "下": "down",
    "前": "front",
    "前へ": "front",
    "前に": "front",
    "後ろ": "back",
    "後ろへ": "back",
    "後ろに": "back",
}

COMMANDS = (
    "open", "close", "right", "left",
    "up", "down", "front", "back", "work", "storage", "none"
)

SCHEMA = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "enum": list(COMMANDS)
        }
    },
    "required": ["command"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "あなたはSO-101ロボットアームの命令分類器です。"
    "開くはopen、閉じる・掴むはclose、"
    "右はright、左はleft、"
    "上げるはup、下げるはdown、"
    "前はfront、後ろはback。"
    "起動や作業基準位置へ移動する指示はwork、""格納位置に戻す指示はstorage、""該当しない指示はnone。"
    "JSONのみを返してください。"
)

def classify(spoken):
    payload = {
        "model": "qwen3:1.7b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": spoken},
        ],
        "format": SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({})
    )

    with opener.open(request, timeout=30) as response:
        result = json.load(response)

    content = result["message"]["content"]
    command = json.loads(content).get("command", "none")
    return command if command in COMMANDS else "none"


if __name__ == "__main__":
    print("=== SO-101 音声8動作 分類テスト ===")
    print("ロボットへの移動指令は送信しません。")
    print("日本語を入力してください。終了は exit")

    while True:
        spoken = input("\n指示 > ").strip()
        spoken = spoken.replace(" ", "").replace("　", "")

        if spoken.lower() == "exit":
            break

        expected = ALLOWED.get(spoken)

        if expected is None:
            print("未登録の指示 → 拒否")
            continue

        try:
            actual = classify(spoken)
        except Exception as e:
            print("LLM通信エラー:", e)
            continue

        print(f"許可リスト : {expected}")
        print(f"Qwen3判定  : {actual}")

        if expected == actual:
            print("OK：分類一致（実機は動きません）")
        else:
            print("NG：分類不一致（拒否）")

    print("テスト終了")
