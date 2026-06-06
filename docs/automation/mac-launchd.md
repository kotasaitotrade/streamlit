# Mac での 30分ごと自動実行

**Mac の launchd で、30分ごとに sedori-tool を自動実行します。**

⏱️ **所要時間: 約 10 分**

---

## 📋 このページで行うこと

1. ✅ launchd 設定ファイルを作成
2. ✅ sedori-tool の自動実行スクリプトを実行
3. ✅ 動作確認

---

## ⚠️ 注意

Mac では、セットアップ時に自動実行スクリプトが自動的に `setup_autoschedule.sh` という形で提供されます。

---

## ステップ 1: 自動実行スクリプトを実行

### 1-1. ターミナルを開く

**Command + Space** を押して、「ターミナル」と検索：

```
Spotlight 検索:
🔍 ターミナル
  └─ ターミナル.app ← クリック
```

### 1-2. スクリプトを実行

ターミナルに以下のコマンドをコピー＆ペーストして **Enter**：

```bash
cd ~/Desktop/sedori-tool-mac/bin
./setup_autoschedule.sh
```

**ターミナル画面:**

```
┌──────────────────────────────────────┐
│ Terminal (zsh)                        │
├──────────────────────────────────────┤
│                                      │
│ $ cd ~/Desktop/sedori-tool-mac/bin
│ $ ./setup_autoschedule.sh
│
│ ==================================================
│   launchd 自動実行スケジュール設定
│ ==================================================
│
│ [info] plist ファイルを作成中...
│ [success] com.sedoritool.autoschedule.plist
│          ~/Library/LaunchAgents/ に作成しました
│
│ [info] launchd に登録中...
│ [success] launchd に登録完了
│
│ [info] 設定確認中...
│ ✅ 30分ごとに自動実行するように設定されました
│
│ 開始時刻: 09:00
│ 繰り返し間隔: 30分
│ 実行プログラム: 4_メルカリ値下げ.sh
│
│ ==================================================
│ ✅ 自動実行設定が完了しました！
│ ==================================================
│
│ $
│
└──────────────────────────────────────┘
```

✅ **自動実行設定が完了しました！**

---

## ステップ 2: 動作確認

### 2-1. ログファイルで確認

自動実行時に以下の場所にログが記録されます：

```bash
cat ~/Desktop/sedori-tool-mac/log/autoschedule.log
```

**ログ表示例:**

```
┌──────────────────────────────────────┐
│ Terminal (zsh)                        │
├──────────────────────────────────────┤
│                                      │
│ $ cat ~/Desktop/sedori-tool-mac/log/ │
│ autoschedule.log                     │
│                                      │
│ [2026-06-06 09:00:15] メルカリ値下げ │
│ [2026-06-06 09:00:16] 対象商品を検索 │
│ [2026-06-06 09:00:23] 値下げ完了     │
│ [2026-06-06 09:00:24] Discord に通知 │
│ [2026-06-06 09:00:25] 成功           │
│                                      │
│ $
│
└──────────────────────────────────────┘
```

### 2-2. Discord 通知で確認

設定した Discord チャンネルで、値下げ通知が届いているか確認：

```
📉 メルカリ値下げ完了

iPhone SE 第3世代
定価: ¥9,999 → 新価格: ¥9,499
-¥500 値下げ

実行時刻: 2026-06-06 09:00:25
```

### 2-3. launchd の状態確認

ターミナルで以下を実行して、launchd に登録されているか確認：

```bash
launchctl list | grep sedori
```

**出力例:**

```
$ launchctl list | grep sedori
12345  -  0  com.sedoritool.autoschedule

$ 
```

- **12345**: プロセス ID
- **-**: CPU 使用率（実行中でない場合は `-`）
- **0**: 終了コード（0 = 成功）

---

## ⚙️ 詳細設定

### 実行時刻を変更したい場合

plist ファイルを編集します：

```bash
nano ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
```

**編集内容:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sedoritool.autoschedule</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/Users/(ユーザー名)/Desktop/sedori-tool-mac/4_メルカリ値下げ.sh</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <array>
        <!-- 09:00 に実行 -->
        <dict>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- 09:30 に実行 -->
        <dict>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
        <!-- ... 以降 30分ごとの時刻を追加 -->
    </array>
    
    <key>StandardOutPath</key>
    <string>/Users/(ユーザー名)/Desktop/sedori-tool-mac/log/autoschedule.log</string>
    
    <key>StandardErrorPath</key>
    <string>/Users/(ユーザー名)/Desktop/sedori-tool-mac/log/autoschedule_error.log</string>
</dict>
</plist>
```

編集後、以下を実行して反映：

```bash
launchctl unload ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
launchctl load ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
```

---

## ❌ 自動実行が動作しない場合

### トラブル 1: スクリプトが実行されない

**対応方法:**
1. ログファイルを確認
2. スクリプトの実行権限を確認

```bash
ls -l ~/Desktop/sedori-tool-mac/bin/
chmod +x ~/Desktop/sedori-tool-mac/bin/*.sh
```

### トラブル 2: launchd に登録されていない

**確認:**
```bash
launchctl list | grep sedori
```

**登録されていない場合:**
```bash
launchctl load ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
```

### トラブル 3: スリープ中は実行されない

Mac のスリープモード中は自動実行されません。

**対応方法:**
1. システム環境設定 → 省エネルギー
2. 「コンピュータをスリープさせない」に設定
3. または、cron を使用

```bash
crontab -e

# 以下を追加（30分ごとに実行）
*/30 * * * * ~/Desktop/sedori-tool-mac/4_メルカリ値下げ.sh
```

### トラブル 4: Permission denied エラー

**エラー表示:**
```
[error] Permission denied
```

**対応方法:**
```bash
chmod +x ~/Desktop/sedori-tool-mac/bin/*.sh
chmod +x ~/Desktop/sedori-tool-mac/4_*.sh
```

---

## 🔧 自動実行を解除したい場合

自動実行を一時的に無効にする場合：

```bash
launchctl unload ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
```

再度有効にする場合：

```bash
launchctl load ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
```

完全に削除する場合：

```bash
rm ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
launchctl unload ~/Library/LaunchAgents/com.sedoritool.autoschedule.plist
```

---

## 📋 チェックリスト

Mac での自動実行設定が完了しているか確認：

- [ ] `setup_autoschedule.sh` を実行した
- [ ] ターミナルに「✅ 自動実行設定が完了しました！」と表示された
- [ ] `launchctl list | grep sedori` で登録を確認した
- [ ] ログファイルに実行結果が記録されている
- [ ] Discord に値下げ通知が届いている

✅ すべてチェックできたら、自動実行の設定は完了です。

---

## 🎯 次のステップ

Mac での自動実行設定が完了しました！

これからは、寝ている間も自動で新着監視・値下げが実行されます。

👉 **[トラブルシューティング →](../troubleshoot/faq.md)**

---

**準備完了！次のステップへ → [トラブルシューティング](../troubleshoot/faq.md)**

*最終更新: 2026-06-06 | バージョン: 1.0*
