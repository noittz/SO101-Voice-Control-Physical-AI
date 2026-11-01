# 公開前チェックリスト

- [ ] `voice_bridge_v3_success.py` と `voice_poses_classifier_v2.py` の**実際のソース**を安全確認後に追加
- [ ] 追加したファイルのAPIキー、パスワード、トークン、認証URLを調査
- [ ] Windowsユーザー名・メール・個人フォルダーのパス、USBシリアル番号を削除/汎用化
- [ ] `.env`、校正JSON、voice_command.json、ログ、バックアップ、venv、学習モデルをGitに含めていない
- [ ] 動画・写真の画面に個人情報、アカウント情報、鍵、固有シリアル番号が映らない
- [ ] `python scripts/scan_secrets.py .` を実施し、ヒットはすべて手動確認
- [ ] `git status --short` と `git ls-files` で追跡ファイルを目視確認
- [ ] git add の後、`git diff --cached --name-only` と `git diff --cached` を確認
- [ ] 意図せず秘密をコミットした場合は公開を停止し、秘密をローテーション（履歴削除だけでは不足）
- [ ] READMEの不足ファイル・YouTube URL・動作条件を更新
