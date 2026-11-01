"""SO-101 voice pose controller v9 VIDEO DEMO. DRY RUN by default.
A one-time startup ARM confirmation is retained. In --video-demo mode,
per-command YES is omitted for a limited number of accepted motions.
"""
import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT = Path.home() / "lerobot_project"
sys.path.insert(0, str(PROJECT))
from voice_poses_classifier_v2 import classify

BASE = Path.home() / "so101_poses"
VOICE_FILE = Path(os.environ.get("SO101_VOICE_FILE", str(Path("/mnt/c/Users/Owner/so101_voice/voice_command.json"))))
SERIAL = os.environ.get("SO101_FOLLOWER_SERIAL", "")
MOTORS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
FPS = 20
STEP_DEG = 0.3
TOLERANCE = 3.0
ERROR_LIMIT = 6.0
STAGE_TIMEOUT = 180.0
MAX_AGE = 8.0
VIDEO_MAX_MOVES = 6
VIDEO_MAX_SECONDS = 600.0

# Independent Python rule: do not auto-correct ambiguous ASR errors.
WORK = {"起動", "起動して", "起動してください", "作業基準位置に行け", "作業位置に移動", "作業位置に行って", "作業基準位置に行ってください", "作業基準位置へ移動して"}
STORAGE = {"格納", "格納して", "格納してください", "格納位置に戻って"}
UNCERTAIN = {"作業基準市に行ってください"}


def normalize(value):
    return re.sub(r"[\s、。！？!?]", "", str(value))


def python_judge(text):
    if text in WORK:
        return "work", "clear"
    if text in STORAGE:
        return "storage", "clear"
    if text in UNCERTAIN:
        return "work", "confirm"
    return "none", "reject"


def read_voice():
    data = json.loads(VOICE_FILE.read_text(encoding="utf-8-sig"))
    return float(data["timestamp"]), normalize(data.get("text", ""))


def load_pose(filename):
    data = json.loads((BASE / filename).read_text(encoding="utf-8"))
    if data["robot_id"] != "so101_follower":
        raise RuntimeError("保存データのロボットIDが一致しません")
    positions = {k: float(v) for k, v in data["positions"].items()}
    if set(positions) != set(MOTORS) or not all(math.isfinite(v) for v in positions.values()):
        raise RuntimeError("保存データの関節構成または値が不正です")
    return positions


def near(a, b, limit):
    return all(abs(a[k] - b[k]) <= limit for k in MOTORS)


class RobotController:
    def __init__(self, video_demo=False):
        self.video_demo = video_demo
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
        if not SERIAL:
            raise RuntimeError("SO101_FOLLOWER_SERIAL を設定してください")
        matches = list(Path("/dev/serial/by-id").glob(f"*{SERIAL}*"))
        if len(matches) != 1:
            raise RuntimeError("FollowerのUSBシリアルを一意に検出できません")
        self.robot = SO101Follower(SO101FollowerConfig(
            port=str(matches[0].resolve()),
            id="so101_follower",
            max_relative_target=5.0,
            disable_torque_on_disconnect=True,
        ))
        self.torque_attempted = False
        self.storage = load_pose("storage_pose.json")
        self.middle = load_pose("transition_pose.json")
        self.work = load_pose("work_home.json")

    def position(self):
        observation = self.robot.get_observation()
        values = {k: float(observation[f"{k}.pos"]) for k in MOTORS}
        if not all(math.isfinite(v) for v in values.values()):
            raise RuntimeError("位置センサー値が不正です")
        return values

    def connect(self):
        self.robot.connect(calibrate=False)
        pos = self.position()
        if not (near(pos, self.storage, 8.0) or near(pos, self.work, 8.0)):
            raise RuntimeError("開始位置が格納/作業位置のどちらでもありません。トルクを投入しません")
        print("現在位置確認OK。動作経路、電源断時の落下対策、非常停止手段を確認してください。")
        if input("トルクを投入する場合だけ ARM と入力 > ").strip() != "ARM":
            raise RuntimeError("操作を取り消しました")
        self.robot.bus.sync_write("Goal_Position", pos)
        self.torque_attempted = True
        self.robot.bus.enable_torque()
        time.sleep(0.2)
        if not near(pos, self.position(), 3.0):
            raise RuntimeError("トルク投入時に位置が変化したため中断")
        print("保持トルクON。中間位置でもトルクは解除しません。")

    def stage(self, label, target):
        print(f"\n=== {label} へ移動開始 ===", flush=True)
        command = self.position().copy()
        deadline = time.monotonic() + STAGE_TIMEOUT
        last_print = 0.0
        while time.monotonic() < deadline:
            actual = self.position()
            if near(actual, target, TOLERANCE):
                print(f"{label}: 到達判定OK（各関節±{TOLERANCE}以内）", flush=True)
                return
            errors = {k: abs(command[k] - actual[k]) for k in MOTORS}
            if any(v > ERROR_LIMIT for v in errors.values()):
                raise RuntimeError(f"{label}: 追従誤差が大きいため指令停止 {errors}")
            for k in MOTORS:
                diff = target[k] - command[k]
                step = 0.2 if k == "gripper" else STEP_DEG
                command[k] += max(-step, min(step, diff))
            self.robot.send_action({f"{k}.pos": v for k, v in command.items()})
            now = time.monotonic()
            if now - last_print >= 3:
                print(f"{label}: 残り最大角度差={max(abs(actual[k]-target[k]) for k in MOTORS):.2f}", flush=True)
                last_print = now
            time.sleep(1 / FPS)
        raise RuntimeError(f"{label}: 到達タイムアウト")

    def execute(self, command):
        current = self.position()
        if command == "work":
            if not near(current, self.storage, 8.0):
                print("拒否：現在位置が格納位置ではありません")
                return
            route = (("中間位置", self.middle), ("作業基準位置", self.work))
            title = "起動"
        elif command == "storage":
            if not near(current, self.work, 8.0):
                print("拒否：現在位置が作業基準位置ではありません")
                return
            route = (("中間位置", self.middle), ("格納位置", self.storage))
            title = "格納"
        else:
            return
        print(f"\n{title}経路: " + " → ".join(name for name, _ in route))
        if self.video_demo:
            print("撮影モード：開始時にARM確認済みのため、個別YESは省略します")
        elif input("周囲の安全を確認し、実行する場合だけ YES > ").strip() != "YES":
            print("動作を取り消しました")
            return
        print(f"【{title}処理開始】")
        for name, pose in route:
            self.stage(name, pose)
        print(f"【{title}完了】（位置センサーによる許容誤差内判定）", flush=True)

    def close(self):
        if not self.robot.bus.is_connected:
            return
        if self.torque_attempted:
            try:
                self.robot.bus.sync_write("Goal_Position", self.position())
                print("現在位置への保持指令を送信しました")
            except Exception as exc:
                print("警告：保持指令に失敗:", exc)
        # Never auto-drop torque: arm can collapse under gravity.
        while True:
            try:
                response = input("\nアームを物理的に支持した後、RELEASE と入力 > ").strip()
                if response == "RELEASE":
                    break
            except (KeyboardInterrupt, EOFError):
                print("安全な支持を確認してください。強制終了はしないでください")
        self.robot.bus.disconnect(disable_torque=True)
        print("ロボット切断完了")


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


def main():
    log_dir = PROJECT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / ("so101_voice_v9_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
    log_stream = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.__stdout__, log_stream)
    print(f"ログ保存先: {log_path}")
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="実機制御を有効化する（手動確認必須）")
    parser.add_argument("--video-demo", action="store_true", help="撮影時のみ個別YES省略。--live必須、開始時ARMは維持")
    args = parser.parse_args()
    if args.video_demo and not args.live:
        parser.error("--video-demo は --live と同時指定してください")
    controller = None
    demo_moves = 0
    demo_started_at = time.monotonic()
    last_timestamp = 0.0
    if VOICE_FILE.exists():
        try:
            last_timestamp, _ = read_voice()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
    print("=== SO-101 音声AI姿勢制御 v9 ===", flush=True)
    print("MODE:", "LIVE 撮影モード（開始時ARMのみ、最大6動作/10分）" if args.video_demo else ("LIVE（毎回YES確認）" if args.live else "DRY RUN（実機は動きません）"), flush=True)
    try:
        if args.live:
            controller = RobotController(video_demo=args.video_demo)
            controller.connect()
        print("Voskの新しい音声入力を待機中。終了は Ctrl+C", flush=True)
        while True:
            if args.video_demo and (demo_moves >= VIDEO_MAX_MOVES or time.monotonic() - demo_started_at >= VIDEO_MAX_SECONDS):
                print("撮影モードの上限に達しました。終了します。")
                break
            try:
                timestamp, spoken = read_voice()
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                time.sleep(0.2)
                continue
            if timestamp <= last_timestamp:
                time.sleep(0.2)
                continue
            last_timestamp = timestamp
            if not spoken or abs(time.time() - timestamp) > MAX_AGE:
                print("空または古い発話を拒否")
                continue
            print(f"\nVosk書き起こし: {spoken}", flush=True)
            expected, status = python_judge(spoken)
            try:
                actual = classify(spoken)
            except Exception as exc:
                print(f"LLM通信エラーにつき拒否: {exc}")
                continue
            print(f"Python判定: {expected} ({status})")
            print(f"Qwen3判定 : {actual}")
            if status != "clear" or expected != actual or expected not in ("work", "storage"):
                print("拒否：独立判定の不一致、曖昧さ、または未許可発話")
                continue
            print("判定一致：動作候補として受理")
            if controller is None:
                if actual == "work":
                    print("DRY RUN：格納位置 → 中間位置 → 作業基準位置 → 起動完了")
                else:
                    print("DRY RUN：作業基準位置 → 中間位置 → 格納位置 → 格納完了")
            else:
                # Voice arriving during movement is not consumed as a new command.
                controller.execute(actual)
                if args.video_demo:
                    demo_moves += 1
                    print(f"撮影モード実行済み：{demo_moves}/{VIDEO_MAX_MOVES}")
                # Skip any voice result generated during movement or confirmation.
                try:
                    last_timestamp = max(last_timestamp, read_voice()[0])
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    pass
    except KeyboardInterrupt:
        print("\n終了要求を受け付けました。", flush=True)
    except Exception as exc:
        print(f"\nSTOP: {type(exc).__name__}: {exc}", flush=True)
    finally:
        if controller is not None:
            controller.close()


if __name__ == "__main__":
    main()
