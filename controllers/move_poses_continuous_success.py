import os
import json
import math
import time
from pathlib import Path

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

BASE = Path.home() / "so101_poses"
SERIAL = os.environ.get("SO101_FOLLOWER_SERIAL", "").strip()

MOTORS = [
    "shoulder_pan", "shoulder_lift", "elbow_flex",
    "wrist_flex", "wrist_roll", "gripper"
]

FPS = 20
STEP = 0.3
ERROR_LIMIT = 6.0
TOLERANCE = 3.0
STAGE_TIMEOUT = 180.0

def load_pose(filename):
    data = json.loads(
        (BASE / filename).read_text(encoding="utf-8")
    )
    if data["robot_id"] != "so101_follower":
        raise RuntimeError("ロボットIDが一致しません")
    pos = {k: float(v) for k, v in data["positions"].items()}
    if set(pos) != set(MOTORS):
        raise RuntimeError("関節構成が一致しません")
    if not all(math.isfinite(v) for v in pos.values()):
        raise RuntimeError("保存値が不正です")
    return pos

storage = load_pose("storage_pose.json")
middle = load_pose("transition_pose.json")
work = load_pose("work_home.json")

ports = list(Path("/dev/serial/by-id").glob(f"*{SERIAL}*"))
if len(ports) != 1:
    raise RuntimeError("白いFollowerが見つかりません")

robot = SO101Follower(SO101FollowerConfig(
    port=str(ports[0].resolve()),
    id="so101_follower",
    max_relative_target=5.0,
    disable_torque_on_disconnect=True,
))

torque_attempted = False

def read_position():
    obs = robot.get_observation()
    pos = {k: float(obs[f"{k}.pos"]) for k in MOTORS}
    if not all(math.isfinite(v) for v in pos.values()):
        raise RuntimeError("位置の読み取り値が不正です")
    return pos

def near(a, b, limit):
    return all(abs(a[k] - b[k]) <= limit for k in MOTORS)

def hold_current():
    pos = read_position()
    robot.bus.sync_write("Goal_Position", pos)

def move_to(name, target):
    print(f"\n=== {name} へ移動 ===")

    start = read_position()
    command = start.copy()
    deadline = time.monotonic() + STAGE_TIMEOUT
    last_print = 0.0

    while time.monotonic() < deadline:
        actual = read_position()

        if near(actual, target, TOLERANCE):
            print(f"{name}: 到達判定 OK")
            return True

        following = {
            k: abs(command[k] - actual[k]) for k in MOTORS
        }

        if any(v > ERROR_LIMIT for v in following.values()):
            raise RuntimeError(
                f"{name}: 追従誤差が大きいため停止 {following}"
            )

        for k in MOTORS:
            diff = target[k] - command[k]
            step = 0.2 if k == "gripper" else STEP
            command[k] += max(-step, min(step, diff))

        robot.send_action({
            f"{k}.pos": v for k, v in command.items()
        })

        now = time.monotonic()
        if now - last_print > 3:
            errors = {
                k: round(abs(target[k] - actual[k]), 2)
                for k in MOTORS
            }
            print("残りの位置差:", errors)
            last_print = now

        time.sleep(1 / FPS)

    raise RuntimeError(f"{name}: 到達タイムアウト")

try:
    robot.connect(calibrate=False)
    current = read_position()

    print("\n=== 現在の位置 ===")
    for k, v in current.items():
        print(f"{k:16s}: {v:8.2f}")

    if not near(current, storage, 25.0):
        raise RuntimeError(
            "開始位置が格納位置から離れています。"
            "自動移動せず終了します。"
        )

    print("\n移動予定:")
    print("格納位置 → 中間位置 → 作業基準位置")
    print("中間位置ではトルクを解除しません")
    print("終点でも操作待ちの間は姿勢を保持します")

    answer = input("\n経路と安全を確認したら YES: ")

    if answer == "YES":
        robot.bus.sync_write("Goal_Position", current)
        torque_attempted = True
        robot.bus.enable_torque()

        time.sleep(0.2)
        after_enable = read_position()
        if not near(current, after_enable, 3.0):
            raise RuntimeError("トルク投入時に姿勢が変化しました")

        move_to("中間位置", middle)
        move_to("作業基準位置", work)

        print("\n作業基準位置への移動が完了しました")

        while True:
            print("\n次の操作を入力してください")
            print("  storage : 中間位置を経由して格納")
            print("  work    : 中間位置を経由して作業位置")
            print("  release : 支持確認後に終了")

            cmd = input("> ").strip().lower()

            if cmd == "storage":
                if not near(read_position(), work, 8.0):
                    print("作業位置から離れています。移動しません")
                    continue
                move_to("中間位置", middle)
                move_to("格納位置", storage)
                print("格納完了")

                # 格納後は作業位置に戻す操作を受け付ける
                while True:
                    next_cmd = input(
                        "\nwork=作業位置 / release=終了 > "
                    ).strip().lower()
                    if next_cmd == "work":
                        move_to("中間位置", middle)
                        move_to("作業基準位置", work)
                        break
                    if next_cmd == "release":
                        raise SystemExit
                    print("work または release を入力してください")

            elif cmd == "work":
                print("すでに作業基準位置です")

            elif cmd == "release":
                break

            else:
                print("認識できない命令です")

    else:
        print("移動を中止しました")

except KeyboardInterrupt:
    print("\n中断しました。新しい移動指令を停止します。")

except SystemExit:
    print("\n終了操作を受け付けました")

except Exception as e:
    print(f"\nSTOP: {type(e).__name__}: {e}")

finally:
    if robot.bus.is_connected:
        if torque_attempted:
            try:
                hold_current()
                print("現在位置への保持指令を設定しました")
            except Exception as e:
                print("保持指令失敗:", e)

        while True:
            try:
                s = input(
                    "\nアームを物理的に支持したら RELEASE: "
                ).strip()
                if s == "RELEASE":
                    break
            except (KeyboardInterrupt, EOFError):
                print("物理的な支持を確認してください")

        try:
            robot.bus.disconnect(disable_torque=True)
            print("切断完了")
        except Exception as e:
            print("切断エラー:", e)
            print("トルク状態が不明です")

