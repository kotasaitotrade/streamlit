"""お知らせメニューの E2E テスト。

バグ: streamlit_new_item.py のメニュールーティングに「お知らせ」分岐が無く、
     未読警告は出るのにお知らせをクリックしても本文が表示されなかった。
修正: menu.startswith("お知らせ") 分岐を追加し、一覧表示＋「すべて既読にする」を実装。

前提:
  - 環境変数 SESSION_TOKEN ... ログイン済みセッショントークン(URLの ?t=)
  - 環境変数 APP_URL        ... 既定 https://discord-notify-tool.streamlit.app/
  - 任意 MARK_READ=1        ... 「すべて既読にする」まで実行し警告解消を確認（既読状態を変更する）

実行:
  SESSION_TOKEN=xxxx python tests/test_e2e_announcements.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

APP = os.environ.get("APP_URL", "https://discord-notify-tool.streamlit.app/")
TOKEN = os.environ.get("SESSION_TOKEN", "")
MARK_READ = os.environ.get("MARK_READ", "") == "1"
SHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

_fail = 0


def check(cond, msg):
    global _fail
    print(("✅ " if cond else "❌ ") + msg)
    if not cond:
        _fail += 1


def content_frame(pg):
    """Streamlit Cloud はアプリ本体を /~/+/ の子フレームに描画する。"""
    for f in pg.frames:
        if "/~/+/" in f.url:
            return f
    return pg.main_frame


def click_menu(pg, label_text):
    fr = content_frame(pg)
    fr.locator('div[data-testid="stRadio"] label').filter(has_text=label_text).first.click()
    pg.wait_for_timeout(8000)


def body_text(pg):
    return content_frame(pg).inner_text("body")


def main():
    if not TOKEN:
        print("SESSION_TOKEN 未設定のためスキップ（CIでは環境変数を設定して実行）")
        return 0

    url = f"{APP}?t={TOKEN}"
    os.makedirs(SHOT_DIR, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(url, wait_until="domcontentloaded")
        pg.wait_for_timeout(9000)

        # 1) ログイン済みで着地し、通知設定に未読警告が出ている
        txt = body_text(pg)
        check("メニュー" in txt, "ログイン済みでメニューが表示される")
        check("未読のお知らせ" in txt, "通知設定に未読警告が表示される（編集ロック）")
        pg.screenshot(path=os.path.join(SHOT_DIR, "e2e_01_landing.png"), full_page=True)

        # 2) お知らせをクリック → 本文と「すべて既読にする」が表示される（修正の核心）
        click_menu(pg, "お知らせ")
        txt = body_text(pg)
        check("📢 お知らせ" in txt or "すべて既読にする" in txt,
              "お知らせクリックで本文/見出しが表示される（旧バグでは空白）")
        check("すべて既読にする" in txt, "未読ありで『すべて既読にする』ボタンが出る")
        pg.screenshot(path=os.path.join(SHOT_DIR, "e2e_02_oshirase.png"), full_page=True)

        # 3) 任意: 既読化まで実行して警告解消＆編集ロック解除を確認
        if MARK_READ:
            fr = content_frame(pg)
            fr.locator('button:has-text("すべて既読にする")').first.click()
            pg.wait_for_timeout(8000)
            click_menu(pg, "通知設定")
            txt = body_text(pg)
            check("未読のお知らせ" not in txt, "既読化後、通知設定の未読警告が消える（編集解除）")
            pg.screenshot(path=os.path.join(SHOT_DIR, "e2e_03_after_read.png"), full_page=True)

        b.close()

    print(f"\n{'🎉 ALL PASS' if _fail == 0 else f'⚠️ {_fail} 件 失敗'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
