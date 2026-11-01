# SO-101 Voice-Controlled Robot Arm / 音声AIロボットアーム

WindowsのVoskによる音声認識、WSL2のPythonによる独立の許可リスト判定、ローカルOllamaのQwen3による命令分類を組み合わせ、SO-101 Followerの姿勢移動を行う実験プロジェクトです。

## 実現した動作

| 発話 | 移動経路 |
|---|---|
| 「起動」「起動して」 | 格納位置 → 中間位置 → 作業基準位置 |
| 「格納」「格納して」 | 作業基準位置 → 中間位置 → 格納位置 |

音声認識 → Pythonの厳密な照合 → Qwen3の分類 → 両者一致時に動作候補として受理 → ロボットの関節角度を使った段階移動、という構成です。ユーザーの実機テストで往復動作を確認しました。独立の測位機器による終点検証ではありません。

## 評価（簡易試験）

- 「起動して」: 8/10回の動作可能判定
- 「格納して」: 7/10回の動作可能判定
- 合計15/20（75%）。**20試行の予備的結果であり、誤受理率や実機安全性を示す値ではありません。**

## 使用技術

- SO-101 Follower（LeRobotで制御）
- Windows 11 / WSL2 Ubuntu / Python
- Vosk（日本語音声認識）
- Ollama + Qwen3 1.7B（命令の意味分類）
- 6関節の角度フィードバックを使う段階的な姿勢移動

## リポジトリ構成

```text
controllers/
  voice_robot_control_v8.py        # 各移動前にYESを要求する通常版
  voice_robot_control_v9_video.py  # 撮影専用モード（回数・時間制限）
scripts/
  scan_secrets.py                  # 公開前の機密情報検査
config/
  requirements-note.txt
.env.example
.gitignore
```

**重要:** 音声認識プログラム `voice_bridge_v3_success.py`、LLM分類器 `voice_poses_classifier_v2.py`、姿勢作成コードは現在の配布パッケージに未同梱です。公開する場合は実機で使用したソースを手元から追加し、改めて機密情報検査を実施してください。分類器がない状態では本パッケージ単独で動作しません。

## セットアップ概要

1. WindowsにVoskと日本語モデル、マイク入力ライブラリを設定し、音声結果を `voice_command.json` に保存する。
2. WSL2にLeRobot、ロボットを操作できるPython仮想環境、分類器 `~/lerobot_project/voice_poses_classifier_v2.py` を配置する。
3. Ollamaで `qwen3:1.7b` を用意し、分類器の接続先を自分の環境に合わせる。**不要なネットワーク公開は行わない**。
4. 自分のロボットで校正・ティーチングした `~/so101_poses/{storage_pose.json,transition_pose.json,work_home.json}` を用意する。これらは他機体へ流用しない。
5. WSLの環境変数 `SO101_FOLLOWER_SERIAL` に、自分の機体のシリアルを指定する。必要に応じて `SO101_VOICE_FILE` も指定する。

例（WSL）:

```bash
export SO101_FOLLOWER_SERIAL='YOUR_FOLLOWER_USB_SERIAL'
export SO101_VOICE_FILE='/mnt/c/Users/Owner/so101_voice/voice_command.json'
cd ~/lerobot_project
source .venv/bin/activate
python -u /path/to/repo/controllers/voice_robot_control_v8.py  # DRY RUN
```

通常版で実機を動かす場合は `--live`。開始時に `ARM`、発話ごとに `YES` の確認が必要です。撮影専用版の `--live --video-demo` は発話ごとのYESを省略しますが、**危険が増すため安全対策を事前に確認し、監視下の限定デモでのみ使用**してください。停止時はアームを支持してからトルクを解除します。

## 安全上の注意

このコードは研究・実演用の試作です。**安全認証済みではありません。** 音声やLLMは誤認識します。可動範囲を遮蔽・隔離し、接触、落下、挟み込みを防止してください。物理的な非常停止手段を用意し、その機能を別途検証してください。Ctrl+Cやプログラム上の例外処理を非常停止装置の代わりにしないでください。移動前に開始姿勢を確認しますが、開始姿勢付近であることが無条件の安全を保証するものではありません。

## 動画

YouTube: **公開後にURLを追記**

## ソースコード・データの公開範囲

- `backups/`、`.venv/`、モデル、ログ、保存した音声、`.env`、機体固有の姿勢JSON、USBシリアル番号は公開しない。
- OllamaのモデルやLeRobot本体のコードは本リポジトリにコピーしない。各公式の導入手順とライセンスを確認する。
- `scripts/scan_secrets.py` は**簡易スキャナ**です。公開前にコード・Git履歴・画像・動画・個人情報を目視確認してください。
- プログラムは一部の保存場所やネットワークに依存します。公開版の個人環境依存情報は環境変数等に置換しています（置換後の実機動作は未検証）。

## 今後の課題

音声認識精度向上、拒否・誤受理の評価、非常停止の確実性検証、一括起動・終了の堅牢化、より細かい末端位置制御。
