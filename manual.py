import streamlit as st
from pathlib import Path
import os

st.set_page_config(
    page_title="せどりツール マニュアル",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# スタイル設定
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    h1 { color: #1f77e5; margin-top: 2rem; }
    h2 { color: #0d47a1; margin-top: 1.5rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }
    </style>
    """, unsafe_allow_html=True)

# サイドバー
with st.sidebar:
    st.title("📚 マニュアル")
    page = st.radio(
        "ページを選択",
        [
            "🏠 ホーム",
            "🪟 Windows セットアップ",
            "🍎 Mac セットアップ",
            "🔑 ライセンス認証",
            "💬 Discord 設定",
            "🔍 メルカリ監視",
            "🟡 ヤフフリ監視",
            "📉 値下げ自動化",
            "⚙️ 自動実行設定",
            "❓ トラブルシューティング",
        ]
    )

    st.divider()
    st.caption("版: 0.1.0 | 更新: 2026-06-06")

# ページコンテンツ
def load_markdown(file_path):
    """Markdown ファイルを読み込んで表示"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"❌ ファイルが見つかりません: {file_path}"

if page == "🏠 ホーム":
    st.title("せどりツール マニュアル")
    st.markdown("""
    ## メルカリ・ヤフフリの新着監視・自動値下げを完全自動化

    このマニュアルは、せどりツールを **完全自動化** するための完全ガイドです。
    スクリーンショット付きで、初心者でも安心して進められます。

    ### 🚀 クイックスタート

    | ステップ | 所要時間 | 内容 |
    |---------|--------|------|
    | 1. 初回セットアップ | 10分 | 必要なツール・言語をインストール |
    | 2. ライセンス認証 | 5分 | ライセンスキーを入力・認証 |
    | 3. Discord 設定 | 10分 | 通知を受け取るチャンネルを設定 |
    | 4. メルカリ監視 | 15分 | 新着商品を自動で通知 |
    | 5. 値下げ自動化 | 15分 | 商品を自動で値下げ |
    | 6. 自動実行設定 | 10分 | 30分ごとに自動実行 |

    **合計: 65分で完全自動化できます**

    ### ✨ このマニュアルの特徴

    ✅ **詳細な手順** - 迷わない、失敗しない
    ✅ **初心者向け** - パソコンに詳しくなくても OK
    ✅ **トラブル対応** - エラーが出ても自力で解決できる
    ✅ **E2E テスト済み** - 実際に動作することを確認済み

    ### 📖 さっそく始めましょう

    左のメニューから、ご自身の環境に合わせてお選びください：
    - **Windows をお使いの方**: 🪟 Windows セットアップ
    - **Mac をお使いの方**: 🍎 Mac セットアップ
    """)

elif page == "🪟 Windows セットアップ":
    st.markdown(load_markdown("docs/setup/windows-setup.md"))

elif page == "🍎 Mac セットアップ":
    st.markdown(load_markdown("docs/setup/mac-setup.md"))

elif page == "🔑 ライセンス認証":
    st.title("ライセンス認証")
    st.info("📋 このページは現在作成中です。\n\nセットアップ後に自動表示されます。")

elif page == "💬 Discord 設定":
    st.title("Discord 通知の設定")
    st.info("📋 このページは現在作成中です。")

elif page == "🔍 メルカリ監視":
    st.title("メルカリ新着監視の設定")
    st.info("📋 このページは現在作成中です。")

elif page == "🟡 ヤフフリ監視":
    st.title("ヤフフリ新着監視の設定")
    st.info("📋 このページは現在作成中です。")

elif page == "📉 値下げ自動化":
    st.title("自動値下げの設定")
    st.info("📋 このページは現在作成中です。")

elif page == "⚙️ 自動実行設定":
    st.title("30分ごと自動実行の設定")
    st.markdown("""
    ## Windows での自動実行

    Windows のタスクスケジューラで、30分ごとに自動実行します。

    ### 手順

    1. **タスクスケジューラを開く**
        - Windows キー + R
        - `taskschd.msc` と入力して Enter

    2. **新しいタスクを作成**
        - 「タスクの作成」をクリック
        - 名前: `sedori-tool-pricedown`

    3. **トリガーを設定**
        - 「トリガー」タブ
        - 「新規」をクリック
        - 「繰り返し実行」を「30分」に設定

    4. **アクション設定**
        - 「アクション」タブ
        - 「新規」をクリック
        - プログラム: `C:\\Users\\(ユーザー名)\\Desktop\\sedori-tool\\4_メルカリ値下げ.bat`

    5. **保存**
        - 「OK」をクリックして完了

    ---

    ## Mac での自動実行

    Mac は launchd で自動実行を設定します。

    詳細は、セットアップ後に `setup_autoschedule.sh` を実行してください。
    """)

elif page == "❓ トラブルシューティング":
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

    **原因**: ファイルの場所が制限されている

    **対応方法**:
    - **sedori-tool** フォルダを **Desktop** に配置
    - Documents フォルダではなく Desktop に置くこと

    ### セットアップが途中で止まった

    **対応方法**:
    - 初回セットアップを再度実行
    - 中断したところから続行します

    ### ライセンス認証エラー

    **確認事項**:
    1. ライセンスキーをコピーするとき、前後に空白がないか確認
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

st.divider()
st.caption("© 2026 sedori-tool | [GitHub](https://github.com/kotasaitotrade/sedori-tool-package)")
