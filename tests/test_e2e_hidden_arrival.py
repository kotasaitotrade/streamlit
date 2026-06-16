"""隠しページ（新着通知ライセンス購入）の E2E テスト。

前提（デプロイ後に実行）:
  - Streamlit Cloud Secrets に [sedori] hidden_arrival_key を設定済み
  - 環境変数:
      HIDDEN_KEY   ... 合言葉（hidden_arrival_key と同じ値）
      TEST_LOGIN_ID / TEST_LOGIN_PW ... ログイン用テストアカウント（任意）
      APP_URL      ... 既定 https://discord-notify-tool.streamlit.app/

実行:
  HIDDEN_KEY=xxxx TEST_LOGIN_ID=... TEST_LOGIN_PW=... python tests/test_e2e_hidden_arrival.py

検証内容:
  1) 合言葉なし/誤り → 隠しページは出ず通常ログイン画面（情報漏れなし）
  2) 正しい合言葉 + 未ログイン → 「ログインが必要です」の案内が出る
  3) 正しい合言葉 + ログイン → 「新着通知ライセンス」購入ページ＋「購入手続きへ進む」ボタン
     （※実決済は行わない。Stripeへ遷移するボタンの存在まで確認）
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

APP = os.environ.get("APP_URL", "https://discord-notify-tool.streamlit.app/")
KEY = os.environ.get("HIDDEN_KEY", "")
LOGIN_ID = os.environ.get("TEST_LOGIN_ID", "")
LOGIN_PW = os.environ.get("TEST_LOGIN_PW", "")

_fail = 0


def check(cond, msg):
    global _fail
    print(("✅ " if cond else "❌ ") + msg)
    if not cond:
        _fail += 1


def body_text(page) -> str:
    page.wait_for_timeout(9000)  # Streamlit 描画待ち
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})

        # 1) 誤った合言葉 → 通常ログイン（隠しページ要素なし）
        page.goto(f"{APP}?buy=arrival&k=wrong-key", wait_until="domcontentloaded", timeout=60000)
        t = body_text(page)
        check("新着通知ライセンス" not in t, "誤った合言葉では購入ページが出ない")

        if not KEY:
            print("⚠ HIDDEN_KEY 未指定のため、正しい合言葉の検証はスキップ")
            browser.close()
            return

        # 2) 正しい合言葉 + 未ログイン → 案内表示
        page.goto(f"{APP}?buy=arrival&k={KEY}", wait_until="domcontentloaded", timeout=60000)
        t = body_text(page)
        check("ログインが必要" in t, "正しい合言葉＋未ログインで案内が出る")

        # 3) ログインして購入ページ
        if LOGIN_ID and LOGIN_PW:
            # ID / パスワードを入力してログイン
            inputs = page.get_by_role("textbox")
            inputs.nth(0).fill(LOGIN_ID)
            # パスワードは type=password。2番目のtextboxを使う
            try:
                inputs.nth(1).fill(LOGIN_PW)
            except Exception:
                pass
            page.get_by_role("button", name="ログイン").first.click()
            t = body_text(page)
            check("新着通知ライセンス" in t, "ログイン後に新着通知ライセンス購入ページが表示")
            check("購入手続きへ進む" in t, "「購入手続きへ進む」ボタンが表示")
        else:
            print("⚠ TEST_LOGIN_ID/PW 未指定のため、ログイン後の検証はスキップ")

        browser.close()


if __name__ == "__main__":
    run()
    if _fail:
        print(f"\n{_fail} 件失敗")
        sys.exit(1)
    print("\nE2E OK")
