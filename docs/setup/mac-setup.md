# Mac での初回セットアップ

このページでは、Mac でせどりツールをセットアップする手順を **完全にガイド** します。

⏱️ **所要時間: 約 15 分**

---

## 📋 このページで行うこと

1. ✅ ダウンロード
2. ✅ 展開（解凍）
3. ✅ セキュリティ署名の修正
4. ✅ 初回セットアップの実行
5. ✅ セットアップ完了の確認

---

## ステップ 1: ダウンロード

### 1-1. Google Drive からダウンロード

Safari または Chrome で以下のリンクを開いてください：

> **[sedori-tool-mac.tar.gz をダウンロード](https://drive.google.com/file/d/YOUR_FILE_ID/view?usp=sharing)**

または、Google Drive で検索：

1. [Google Drive](https://drive.google.com) を開く
2. 検索ボックスに **「sedori-tool-mac」** と入力
3. 検索結果から **sedori-tool-mac.tar.gz** をクリック
4. 右上の **⬇️ ダウンロード** ボタンをクリック

### 1-2. ダウンロード完了を確認

Finder を開いて、**ダウンロード** フォルダを確認：

```
~/Downloads/sedori-tool-mac.tar.gz
```

✅ ファイルが見えれば OK です。

---

## ステップ 2: 展開（解凍）

### 2-1. Finder で展開

1. Finder の **ダウンロード** フォルダを開く
2. **sedori-tool-mac.tar.gz** をダブルクリック
3. 自動的に展開されます

### 2-2. デスクトップに移動

展開後、**sedori-tool-mac** フォルダが作成されます。

これを **Desktop** に移動：

```bash
# ターミナルを開く（Command + Space で「ターミナル」と検索）
cd ~/Downloads
mv sedori-tool-mac ~/Desktop/

# 確認
ls ~/Desktop/sedori-tool-mac
```

✅ デスクトップに **sedori-tool-mac** フォルダが見えれば OK です。

---

## ステップ 3: セキュリティ署名の修正

> **Mac のセキュリティ機能により、実行ファイルがブロックされています。**  
> **この手順で解除します。**

### 3-1. ターミナルを開く

**Command + Space** キーを押して、検索ボックスに「ターミナル」と入力：

```
ターミナル.app
```

これをクリック

### 3-2. 以下のコマンドを実行

ターミナルに以下をコピー＆ペーストして **Enter**：

```bash
cd ~/Desktop/sedori-tool-mac
xattr -rd com.apple.quarantine bin/monitor bin/pricedown
```

**出力例:**
```
$ cd ~/Desktop/sedori-tool-mac
$ xattr -rd com.apple.quarantine bin/monitor bin/pricedown
$ 
```

✅ エラーなく完了すれば OK です。

---

## ステップ 4: 初回セットアップの実行

### 4-1. セットアップスクリプトを実行

Finder で **Desktop** → **sedori-tool-mac** を開き、

以下のファイルをダブルクリック：

```
0_初回セットアップ.sh
```

または、ターミナルで実行：

```bash
cd ~/Desktop/sedori-tool-mac
./0_初回セットアップ.sh
```

### 4-2. セットアップ実行中の画面

以下のようなメッセージが表示されます：

```
==================================================
  必要環境のセットアップを開始します
==================================================
[info] Homebrew 確認...
[info] Python 3.10 確認...
[info] 必要ライブラリをインストール中...
```

### 4-3. セットアップ完了を待つ

以下が表示されるまで待ってください：

```
==================================================
✅ セットアップ完了！
次は「2_設定画面を開く.sh」を実行してください。
==================================================
```

> ⚠️ **初回は 5〜10 分かかります。** 気長にお待ちください。

---

## ステップ 5: セットアップ完了の確認

### 5-1. フォルダを確認

Finder で **sedori-tool-mac** フォルダを開き、以下を確認：

```
📁 sedori-tool-mac/
├─ 0_初回セットアップ.sh
├─ 1_設定画面を開く.sh
├─ 📁 config/          ← ここに設定ファイルがある
├─ 📁 log/             ← ここにログが記録される
├─ 📁 src/             ← ツールのコード
└─ 📁 bin/             ← 実行ファイル（monitor, pricedown）
```

### 5-2. 初回セットアップ再実行は不要

セットアップは 1 回だけで OK です。

次は **ライセンス認証** に進みます。

---

## 🎉 セットアップ完了！

**おめでとうございます！** Mac での初回セットアップが完了しました。

次のステップに進みましょう：

👉 **[次へ: ライセンス認証](./license-auth.md)**

---

## ❌ トラブルが出た場合

### 「コマンドが見つかりません」

**原因**: Homebrew がインストールされていない

**対応方法**:

1. ターミナルで以下を実行：
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

2. インストール完了後、セットアップを再実行

### 「Permission denied」

**原因**: スクリプトに実行権限がない

**対応方法**:

```bash
cd ~/Desktop/sedori-tool-mac
chmod +x *.sh
./0_初回セットアップ.sh
```

### セットアップが途中で止まった

**対応方法**:

```bash
cd ~/Desktop/sedori-tool-mac
./0_初回セットアップ.sh
```

もう一度実行してください。中断したところから続行します。

---

## 📞 それでも解決しない場合

ログファイルを確認：

```bash
cat ~/Desktop/sedori-tool-mac/log/*.log
```

[よくあるエラー](../troubleshoot/faq.md) も参照してください。

---

**準備完了！次のステップへ → [ライセンス認証](./license-auth.md)**

*最終更新: 2026-06-06*
