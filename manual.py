import streamlit as st

st.set_page_config(
    page_title="せどりツール マニュアル",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
    .main { padding: 2rem; }
    h1 { color: #1f77e5; margin-top: 2rem; }
    h2 { color: #0d47a1; margin-top: 1.5rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }
    </style>
    """, unsafe_allow_html=True)


def load_markdown(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"❌ ファイルが見つかりません: {file_path}"


def img(path, caption=None, small=False):
    if small:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(path, caption=caption, use_container_width=True)
    else:
        st.image(path, caption=caption, use_container_width=True)


# ─────────────────────────────────────────────
# ページ定義
# ─────────────────────────────────────────────

def page_home():
    st.title("せどりツール マニュアル")
    st.markdown("""
    ## メルカリ・ヤフフリの新着監視・自動値下げを完全自動化

    このマニュアルは、せどりツールを **完全自動化** するための完全ガイドです。
    スクリーンショット付きで、初心者でも安心して進められます。

    ### 🚀 クイックスタート

    | ステップ | 所要時間 | 内容 |
    |---------|--------|------|
    | 1. 初回セットアップ | 10分 | ダウンロード・インストール |
    | 2. ライセンス認証 | 5分 | ライセンスキーを入力・認証 |
    | 3. Discord 設定 | 10分 | 通知を受け取るチャンネルを設定 |
    | 4. メルカリ監視 | 15分 | 新着商品を自動で通知 |
    | 5. 値下げ自動化 | 15分 | 商品を自動で値下げ |
    | 6. 起動・確認 | 5分 | ツールを起動して動作確認 |

    **合計: 約 60 分で完全自動化できます**

    ### ✨ このマニュアルの特徴

    ✅ **詳細な手順** - 迷わない、失敗しない
    ✅ **スクリーンショット付き** - 画面を見ながら進められる
    ✅ **初心者向け** - パソコンに詳しくなくても OK
    ✅ **トラブル対応** - エラーが出ても自力で解決できる

    ### 📖 さっそく始めましょう

    左のメニューから、ご自身の環境に合わせてお選びください：
    - **Windows をお使いの方**: 🪟 Windows セットアップ
    - **Mac をお使いの方**: 🍎 Mac セットアップ
    """)


def page_windows():
    st.markdown(load_markdown("docs/setup/windows-setup.md"))


def page_mac():
    st.title("Mac での初回セットアップ")
    st.markdown("⏱️ **所要時間: 約 15 分**")

    st.markdown("""
    ## 📋 このページで行うこと

    1. ✅ ダウンロード（ダウンロード管理画面から DMG を取得）
    2. ✅ インストール（Applications フォルダへ）
    3. ✅ 初回起動（Gatekeeper 解除）
    4. ✅ セットアップ自動実行・設定画面の起動
    """)

    st.divider()

    st.header("ステップ 1: ダウンロード")

    st.markdown("### 1-1. ダウンロード管理画面を開く")
    st.markdown("購入後に届いたライセンスキーでダウンロード管理画面（ツウチマネージャー）にアクセスします。")
    img("images/mac/01_download_page.png", "ダウンロード管理画面")

    st.markdown("### 1-2. OS で「mac」を選択")
    st.markdown("OS のドロップダウンを開いて **mac** を選択してください。")
    img("images/mac/02_os_select.png", "「mac」を選択", small=True)

    st.markdown("### 1-3. 「ダウンロードURLを取得」をクリック")
    st.markdown("ボタンをクリックすると、ダウンロードリンクが表示されます。")
    img("images/mac/03_download_link.png", "「ダウンロード」リンクが表示される", small=True)

    st.markdown("### 1-4. ダウンロードを開始")
    st.markdown("""
    **ダウンロード** リンクをクリックします。
    Chrome の警告が出た場合は **「未確認のファイルをダウンロード」** をクリックしてください。
    """)
    img("images/mac/04_chrome_warning.png", "Chrome の警告 → 「未確認のファイルをダウンロード」をクリック", small=True)

    st.markdown("ダウンロードが始まります（約 300MB）。完了まで待ちます。")
    img("images/mac/05_downloading.png", "ダウンロード中", small=True)

    st.success("✅ **sedori-tool-mac-installer.dmg** のダウンロードが完了すれば OK です。")

    st.divider()

    st.header("ステップ 2: インストール")

    st.markdown("""
    ### 2-1. DMG ファイルを開く

    ダウンロードフォルダの **sedori-tool-mac-installer.dmg** をダブルクリックします。
    ウィンドウが開き、**sedori-tool** アイコンと **Applications** フォルダが表示されます。
    """)
    img("images/mac/06_dmg_open.png", "DMG を開くと Applications と sedori-tool が表示される")

    st.markdown("""
    ### 2-2. Applications フォルダにドラッグ

    **sedori-tool** アイコンを **Applications** フォルダにドラッグ＆ドロップします。
    コピーが完了したら DMG ウィンドウを閉じて構いません。

    ### 2-3. インストール確認

    Launchpad（ロケットアイコン）を開いて、**sedori-tool** が表示されていれば OK です。
    """)
    img("images/mac/07_launchpad.png", "Launchpad に sedori-tool が表示される")

    st.divider()

    st.header("ステップ 3: 初回起動（Gatekeeper 解除）")

    st.markdown("""
    ### 3-1. sedori-tool をダブルクリック

    Launchpad または Applications フォルダから **sedori-tool** をダブルクリックします。

    > ⚠️ **初回は Mac のセキュリティ機能（Gatekeeper）によりブロックされます。**
    > 以下の手順で解除してください。
    """)
    img("images/mac/08_gatekeeper_error.png", '"sedori-tool" は開いていません エラーが表示される', small=True)

    st.markdown("""
    ### 3-2. システム設定からブロックを解除

    **「完了」** をクリックしてエラーを閉じた後、
    **システム設定** → **「プライバシーとセキュリティ」** を開きます。

    画面下部に「**お使いの Mac を保護するために "sedori-tool" がブロックされました**」と表示されているので、
    **「このまま開く」** をクリックします。
    """)
    img("images/mac/09_privacy_settings.png", "プライバシーとセキュリティ → 「このまま開く」をクリック")

    st.markdown("### 3-3. 確認ダイアログで「このまま開く」をクリック")
    img("images/mac/10_open_confirm.png", "確認ダイアログ → 「このまま開く」", small=True)

    st.markdown("### 3-4. Mac のパスワードを入力")
    st.markdown("Mac のログインパスワードを入力して **OK** をクリックします。")
    img("images/mac/11_password.png", "Mac のパスワードを入力 → OK", small=True)

    st.markdown("""
    ### 3-5. アクセス許可ダイアログに「許可」

    以下のダイアログが順番に表示されます。すべて **「許可」** をクリックしてください。
    """)
    col1, col2 = st.columns(2)
    with col1:
        st.image("images/mac/12_terminal_access.png",
                 caption="「bash がターミナルを制御」→「許可」", use_container_width=True)
    with col2:
        st.image("images/mac/13_desktop_access.png",
                 caption="「ターミナルからデスクトップへのアクセス」→「許可」", use_container_width=True)

    st.divider()

    st.header("ステップ 4: セットアップ自動実行")

    st.markdown("""
    ### 4-1. セットアップが自動で始まる

    ターミナルが自動で開き、必要な環境のセットアップが開始されます。

    > ⏳ **5〜10 分かかります。ターミナルの画面はそのままにしてお待ちください。**
    """)
    img("images/mac/14_setup_running.png", "セットアップが自動実行される")

    st.markdown("""
    ### 4-2. ブラウザが自動で開く

    セットアップが完了すると、ブラウザが自動で開き **せどりツール 設定画面** が表示されます。
    """)
    img("images/mac/15_browser_opened.png", "設定画面がブラウザで自動的に開く")

    st.success("✅ 設定画面が表示されたら、セットアップ完了です！")
    st.info("👉 次は **ライセンス認証** に進んでください。左メニューの「🔑 ライセンス認証」を選択。")

    st.divider()

    st.header("❌ トラブルが出た場合")

    with st.expander("「このまま開く」がシステム設定に表示されない"):
        st.markdown("""
        sedori-tool を一度ゴミ箱に入れ、DMG から再インストールしてください。
        再インストール後、再度ダブルクリックするとブロック通知が表示されます。
        """)

    with st.expander("セットアップが途中で止まった・エラーが出た"):
        st.markdown("""
        **sedori-tool をもう一度ダブルクリック** してください。
        セットアップは途中から再開されます。
        """)

    with st.expander("ブラウザが開かない"):
        st.markdown("""
        ターミナルのセットアップが完了するまでお待ちください（最大 10 分）。
        完了後もブラウザが開かない場合は `http://localhost:8501` に手動でアクセスしてください。
        """)

    with st.expander("再セットアップしたい場合"):
        st.markdown("""
        ターミナルで以下を実行するとやり直せます：
        ```bash
        rm ~/.sedori-tool-setup-done
        rm -rf ~/Desktop/sedori-tool-mac
        ```
        その後、**sedori-tool.app** を再度ダブルクリックしてください。
        """)


def page_license():
    st.title("ライセンス認証")
    st.markdown("⏱️ **所要時間: 約 5 分**")

    st.markdown("""
    ## 📋 このページで行うこと

    1. ✅ ダウンロード管理画面からライセンスキーをコピー
    2. ✅ 設定画面にライセンスキーを貼り付けて認証
    """)

    st.divider()

    st.header("ステップ 1: ライセンスキーをコピー")

    st.markdown("""
    ダウンロード管理画面を開き、ライセンスキー欄の右にある **コピーボタン（□）** をクリックします。
    OS は **mac** を選択しておいてください。
    """)
    img("images/mac/16_license_copy.png", "ライセンスキーの右のボタンでコピー")

    st.divider()

    st.header("ステップ 2: 設定画面でライセンスキーを認証")

    st.markdown("""
    設定画面（ブラウザ）の **① ライセンス** タブを開き、
    「ライセンスキー」欄にコピーしたキーを貼り付けます。
    その後、**「🔑 ライセンスを確認」** ボタンをクリックします。
    """)
    img("images/mac/17_license_input.png", "ライセンスキーを貼り付けて「ライセンスを確認」をクリック")

    st.divider()

    st.header("ステップ 3: 認証完了を確認")

    st.markdown("""
    緑色のメッセージ「✅ プラン: AllFull / 使える機能: ...」が表示されれば認証成功です。
    """)
    img("images/mac/18_license_verified.png", "ライセンス認証完了")

    st.success("✅ 認証完了！次は Discord 設定に進みましょう。")
    st.info("👉 左メニューの「💬 Discord 設定」を選択してください。")


def page_discord():
    st.title("Discord 通知の設定")
    st.markdown("⏱️ **所要時間: 約 10 分**")

    st.markdown("""
    ## 📋 このページで行うこと

    1. ✅ Discord でウェブフック URL を作成・コピー
    2. ✅ 設定画面に URL を貼り付けて保存

    **ウェブフック** とは、Discord のチャンネルに自動でメッセージを送るための URL です。
    """)

    st.divider()

    st.header("ステップ 1: 設定画面の Discord タブを確認")

    st.markdown("設定画面の **② Discord通知** タブを開きます。ここに後でウェブフック URL を貼り付けます。")
    img("images/mac/19_discord_tab.png", "② Discord通知タブ（4つの欄に URL を入力する）")

    st.divider()

    st.header("ステップ 2: Discord でウェブフック URL を作成")

    st.markdown("""
    ### 2-1. Discord アプリを開く

    通知を受け取りたいサーバーを開きます。

    > 📝 チャンネルごとに別の URL を設定できます。
    > 「メルカリ通知用」「ヤフフリ通知用」などチャンネルを分けると便利です。
    """)
    img("images/mac/20_discord_app.png", "Discord アプリ")

    st.markdown("### 2-2. 通知を受け取るチャンネルを選ぶ")
    img("images/mac/21_discord_channels.png", "通知を受け取りたいチャンネルを選ぶ")

    st.markdown("""
    ### 2-3. チャンネルの設定を開く

    チャンネル名の右の **⚙️（設定アイコン）** をクリックします。
    """)
    img("images/mac/22_channel_settings.png", "チャンネルの設定（概要）")

    st.markdown("""
    ### 2-4. 連携サービス → ウェブフック を開く

    左メニューの **「連携サービス」** をクリックし、**「ウェブフック」** を選択します。
    """)
    img("images/mac/23_webhook_service.png", "連携サービス → ウェブフック")

    st.markdown("""
    ### 2-5. ウェブフック URL をコピー

    一覧からウェブフックをクリックして展開し、**「ウェブフックURLをコピー」** をクリックします。

    > 📝 新しく作る場合は「**新しいウェブフック**」ボタンから作成してください。
    """)
    img("images/mac/24_webhook_copy.png", "「ウェブフックURLをコピー」をクリック")

    st.divider()

    st.header("ステップ 3: 設定画面に URL を貼り付けて保存")

    st.markdown("""
    コピーした URL を設定画面の各欄に貼り付けます。
    同じ URL を複数の欄に貼り付けても OK です。

    - **メルカリ 新着通知の通知先**
    - **ヤフフリ 新着通知の通知先**
    - **メルカリ 自動値下げの通知先**
    - **ヤフフリ 自動値下げの通知先**
    """)
    img("images/mac/25_webhook_paste.png", "ウェブフック URL を各欄に貼り付け")

    st.markdown("**「Discord 設定を保存」** ボタンをクリックします。「保存しました」が表示されれば完了です。")
    img("images/mac/26_discord_saved.png", "保存完了（「保存しました」が表示される）")

    st.success("✅ Discord 設定完了！")
    st.info("👉 次は監視する商品の設定です。「🔍 メルカリ監視」を選択してください。")


def page_mercari():
    st.title("メルカリ新着監視の設定")
    st.markdown("⏱️ **所要時間: 約 15 分**")

    st.markdown("""
    ## 📋 このページで行うこと

    1. ✅ 新着監視の基本設定（サイクル間隔など）
    2. ✅ 監視する商品リストの登録
    """)

    st.divider()

    st.header("ステップ 1: 新着監視設定")

    st.markdown("""
    設定画面の **③ 新着監視設定** タブを開きます。

    - **監視サイクル間隔（秒）**: `10` のままで OK
    - **値下げ通知の閾値（%）**: `5.00` のままで OK

    > ⚠️ 監視サイクルを短くしすぎると、メルカリ側からアクセス制限を受けることがあります。

    設定を変更したら **「新着監視設定を保存」** をクリックします。
    """)
    img("images/mac/27_monitor_settings.png", "③ 新着監視設定タブ")

    st.divider()

    st.header("ステップ 2: 監視する商品リストを登録")

    st.markdown("""
    設定画面の **⑤ 監視対象リスト** タブを開き、**「メルカリ用」** タブを選択します。

    ### 各列の意味

    | 列 | 説明 |
    |---|---|
    | 型番 | 監視ジョブの名前（自由に付けて OK、メモ用） |
    | URL | メルカリの検索結果ページの URL（必須） |
    | 除外ワード | タイトルにこれを含む商品は通知しない（カンマ区切り） |
    | 必須ワード | タイトルにこれを含む商品だけ通知（カンマ区切り） |
    | 有効 | `TRUE` で監視 ON / `FALSE` で一時停止 |
    | デフォルト金額 | この金額以下の出品だけ通知（円） |

    表の右上の **「+」** ボタンで行を追加し、セルをクリックして直接編集します。
    編集後は **「メルカリ用監視リストを保存」** をクリックしてください。
    """)
    img("images/mac/29_watchlist.png", "⑤ 監視対象リスト（メルカリ用）")

    st.success("✅ メルカリ監視の設定完了！")
    st.info("👉 次は「🟡 ヤフフリ監視」または「📉 値下げ自動化」に進んでください。")


def page_yahoo():
    st.title("ヤフフリ新着監視の設定")
    st.markdown("⏱️ **所要時間: 約 10 分**")

    st.markdown("""
    ヤフオクフリマ（ヤフフリ）の新着監視設定です。
    設定方法は **メルカリ監視とほぼ同じ** です。

    ## 監視対象リスト（ヤフフリ用）

    設定画面の **⑤ 監視対象リスト** タブを開き、**「ヤフフリ用」** タブを選択します。

    URL 欄には **ヤフオクフリマの検索結果ページの URL** を入力してください。
    編集後は **「ヤフフリ用監視リストを保存」** ボタンをクリックしてください。
    """)
    img("images/mac/30_watchlist_yahoo.png", "⑤ 監視対象リスト → 「ヤフフリ用」タブを選択")

    st.success("✅ ヤフフリ監視の設定完了！")
    st.info("👉 次は「📉 値下げ自動化」に進んでください。")


def page_pricedown():
    st.title("自動値下げの設定")
    st.markdown("⏱️ **所要時間: 約 15 分**")

    st.markdown("""
    ## 📋 このページで行うこと

    1. ✅ 値下げのスケジュール・ルールを設定
    2. ✅ 値下げ対象の商品リストを登録
    """)

    st.divider()

    st.header("ステップ 1: 値下げ設定")

    st.markdown("""
    設定画面の **④ 値下げ設定** タブを開きます。

    ### スケジュール

    | 項目 | 説明 | 推奨値 |
    |---|---|---|
    | 実行間隔（分） | 何分ごとに値下げするか | 60 |
    | 稼働開始時刻（時） | 値下げを開始する時間 | 9 |
    | 稼働終了時刻（時） | 値下げを終了する時間 | 23 |

    ### 通常値下げ

    - **値下げ率（%）**: `1.00` のままで OK（1万円 × 1% = 最低 100 円値下がります）

    設定後は **「値下げ設定を保存」** をクリックしてください。
    """)
    img("images/mac/28_pricedown_settings.png", "④ 値下げ設定タブ")

    st.divider()

    st.header("ステップ 2: 値下げ対象リストに商品を登録")

    st.markdown("""
    設定画面の **⑥ 値下げ対象リスト** タブを開きます。

    ### 各列の意味

    | 列 | 説明 |
    |---|---|
    | 有効 | `TRUE` で値下げ対象 / `FALSE` でスキップ |
    | 商品ID | メルカリ商品 URL 末尾の英数字（例: `m1234567890`） |
    | 商品名（メモ） | 自分用の見分けメモ（空欄でも OK） |
    | 最低価格 | この金額より下には値下げしない（円） |

    > 💡 **⑦ 起動** タブからツールを起動すると、出品中の商品一覧が自動取得されてリストに追加されます。
    """)
    img("images/mac/31_pricelist.png", "⑥ 値下げ対象リスト")

    st.success("✅ 値下げ自動化の設定完了！")
    st.info("👉 「⚙️ 自動実行設定」でツールを起動しましょう。")


def page_launch():
    st.title("ツールの起動・動作確認")
    st.markdown("⏱️ **所要時間: 約 5 分**")

    st.markdown("""
    ## 📋 このページで行うこと

    1. ✅ ツールを起動する
    2. ✅ Discord に通知が届くか確認する
    """)

    st.divider()

    st.header("ステップ 1: ツールを起動する")

    st.markdown("""
    設定画面の **⑦ 起動** タブを開きます。

    起動したいツールのボタンをクリックしてください。
    - **メルカリ 新着通知を起動** → メルカリの新着監視が始まります
    - **ヤフフリ 新着通知を起動** → ヤフフリの新着監視が始まります
    - **メルカリ 自動値下げを起動** → メルカリの自動値下げが始まります
    - **ヤフフリ 自動値下げを起動** → ヤフフリの自動値下げが始まります
    """)
    img("images/mac/32_launch.png", "⑦ 起動タブ（各ボタンをクリックして起動）")

    st.markdown("""
    ボタンをクリックすると、緑色のメッセージ「〇〇を起動しました（別ウィンドウで動いています）」が表示されます。
    """)
    img("images/mac/33_launch_running.png", "「起動しました」メッセージが表示される")

    st.divider()

    st.header("ステップ 2: Discord に通知が届くか確認する")

    st.markdown("しばらく待つと、新着商品が見つかったときに Discord に通知が届きます。")
    img("images/mac/34_discord_notify.png", "Discord に新着通知が届いた様子")

    st.success("🎉 完全自動化の設定が完了しました！")

    st.divider()

    st.header("ツールを止める方法")

    st.markdown("""
    起動したツールを止めるには、ツールが動いているウィンドウで **Ctrl+C** を押してください。
    同じツールを再度起動すると、前のプロセスが自動的に終了します。
    """)


def page_troubleshoot():
    st.title("よくあるエラーと対応")
    st.markdown("""
    ## よくあるエラー

    ### 「Python が見つかりません」

    **原因**: Python がインストールされていない

    **対応方法**:
    1. [Python 3.11 公式サイト](https://www.python.org/downloads/) からダウンロード
    2. インストーラーを実行
    3. **「Add Python to PATH」 にチェック** を入れる
    4. インストール完了後、セットアップを再実行

    ### 「アクセスが拒否されました」

    **対応方法**:
    - **sedori-tool** フォルダを **Desktop** に配置してください

    ### セットアップが途中で止まった

    **対応方法**:
    - 初回セットアップを再度実行してください
    - 中断したところから続行されます

    ### ライセンス認証エラー

    **確認事項**:
    1. ライセンスキーの前後に空白がないか確認
    2. メールを開き直してキーをコピー
    3. もう一度認証を試す

    ---

    ## ログを確認する

    エラーの詳細はログファイルで確認できます：

    ```
    Windows: C:\\Users\\(ユーザー名)\\Desktop\\sedori-tool\\log\\
    Mac: ~/Desktop/sedori-tool-mac/log/
    ```

    ---

    ## 📞 それでも解決しない場合

    ログファイルの内容をコピーして、ご相談ください。
    """)


# ─────────────────────────────────────────────
# ナビゲーション設定
# ─────────────────────────────────────────────

pg = st.navigation(
    [
        st.Page(page_home,         title="ホーム",               icon="🏠", default=True),
        st.Page(page_windows,      title="Windows セットアップ",  icon="🪟"),
        st.Page(page_mac,          title="Mac セットアップ",       icon="🍎"),
        st.Page(page_license,      title="ライセンス認証",         icon="🔑"),
        st.Page(page_discord,      title="Discord 設定",          icon="💬"),
        st.Page(page_mercari,      title="メルカリ監視",           icon="🔍"),
        st.Page(page_yahoo,        title="ヤフフリ監視",           icon="🟡"),
        st.Page(page_pricedown,    title="値下げ自動化",           icon="📉"),
        st.Page(page_launch,       title="自動実行設定",           icon="⚙️"),
        st.Page(page_troubleshoot, title="トラブルシューティング",  icon="❓"),
    ]
)

with st.sidebar:
    st.divider()
    st.caption("版: 0.1.0 | 更新: 2026-06-09")

st.divider()
st.caption("© 2026 sedori-tool | [GitHub](https://github.com/kotasaitotrade/sedori-tool-package)")

pg.run()
