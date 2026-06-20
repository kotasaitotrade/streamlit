"""
お知らせ機能の共通モジュール
- Google Sheets「お知らせ」シートで管理
- 管理者: 投稿 → 全ユーザーへ Discord webhook 通知
- ユーザー: 一覧表示 + 既読管理（USER_COLS の read_announcements 列、CSV形式）
- 未読がある場合は通知設定編集をブロック
"""
import json
import time
import uuid
import requests
import pandas as pd
import streamlit as st
from datetime import datetime

ANNOUNCEMENTS_SHEET_NAME = "お知らせ"
ANNOUNCEMENT_COLS = ['id', 'date', 'title', 'body', 'notified', 'created_by']

# 全ユーザーへの通知に加えて、必ずお知らせを送る固定チャンネル（管理用など）
EXTRA_ANNOUNCEMENT_WEBHOOKS = [
    "https://discord.com/api/webhooks/1517872541421666354/nGJQ3IQlnVVw94eF8IJ0f6goGKBvFAFsxcq-T-_HNrXLTNVYD_5Bu9gKVGCTAz7KoF-r",
]


# ==========================================
#   シート操作
# ==========================================
def _open_sheet(client, spreadsheet_id):
    ss = client.open_by_key(spreadsheet_id)
    try:
        ws = ss.worksheet(ANNOUNCEMENTS_SHEET_NAME)
    except Exception:
        ws = ss.add_worksheet(title=ANNOUNCEMENTS_SHEET_NAME, rows=200, cols=len(ANNOUNCEMENT_COLS))
        ws.append_row(ANNOUNCEMENT_COLS)
    headers = ws.row_values(1)
    missing = [c for c in ANNOUNCEMENT_COLS if c not in headers]
    if missing:
        for h in missing:
            ws.update_cell(1, len(headers) + 1, h)
            headers.append(h)
    return ws


@st.cache_data(ttl=30)
def load_announcements(_client, spreadsheet_id):
    """お知らせ一覧を取得（新しい順）"""
    try:
        ws = _open_sheet(_client, spreadsheet_id)
        data = ws.get_all_values()
        if len(data) < 2:
            return pd.DataFrame(columns=ANNOUNCEMENT_COLS)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        for c in ANNOUNCEMENT_COLS:
            if c not in df.columns:
                df[c] = ''
        # 日付降順
        df = df.sort_values('date', ascending=False).reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame(columns=ANNOUNCEMENT_COLS)


def add_announcement(client, spreadsheet_id, title, body, created_by=''):
    """お知らせを1件追加。idは自動採番（YYYYMMDDHHmmss + 短いhash）"""
    try:
        ws = _open_sheet(client, spreadsheet_id)
        now = datetime.now()
        ann_id = f"{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        date_str = now.strftime('%Y/%m/%d %H:%M')
        row = [ann_id, date_str, str(title), str(body), '', str(created_by)]
        ws.append_row(row)
        load_announcements.clear()
        return True, ann_id
    except Exception as e:
        return False, str(e)


def mark_notified(client, spreadsheet_id, ann_id):
    """お知らせの notified 列を "1" に更新"""
    try:
        ws = _open_sheet(client, spreadsheet_id)
        col_values = ws.col_values(1)
        for i, v in enumerate(col_values):
            if v == str(ann_id):
                headers = ws.row_values(1)
                if 'notified' in headers:
                    col_idx = headers.index('notified') + 1
                    ws.update_cell(i + 1, col_idx, '1')
                load_announcements.clear()
                return True
        return False
    except Exception:
        return False


# ==========================================
#   既読管理
# ==========================================
def parse_read_ids(read_str):
    """CSV形式の既読IDリストをパース"""
    if not read_str or str(read_str).strip().lower() in ('', 'nan', 'none'):
        return set()
    return set(s.strip() for s in str(read_str).split(',') if s.strip())


def serialize_read_ids(read_ids):
    """既読IDセットをCSV文字列化（重複除去・順序維持なし）"""
    return ','.join(sorted(set(read_ids)))


def get_unread_announcements(announcements_df, user_read_str):
    """未読のお知らせ行のみを返す"""
    if announcements_df is None or announcements_df.empty:
        return announcements_df
    read_ids = parse_read_ids(user_read_str)
    return announcements_df[~announcements_df['id'].astype(str).isin(read_ids)]


# ==========================================
#   Discord 通知
# ==========================================
def _post_announcement(url, payload):
    """1つのWebhook URLへお知らせを送信。成功なら True。429はリトライする。"""
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code in [200, 204]:
                return True
            if resp.status_code == 429:
                try:
                    retry_after = float(resp.json().get('retry_after', 1.0))
                except Exception:
                    retry_after = 2.0
                time.sleep(retry_after + 0.5)
                continue
            return False
        except Exception:
            time.sleep(1)
    return False


def send_discord_to_all_users(users_df, title, body, bot_name="お知らせBot"):
    """全ユーザーのチャンネルURL＋固定チャンネルへお知らせを送信。成功/失敗件数を返す"""
    sent = 0
    failed = 0
    embed = {
        "title": f"📢 {title}",
        "color": 0xB5443E,
        "description": str(body)[:3500],
        "footer": {"text": "ツウチマネージャー お知らせ"},
        "timestamp": datetime.now().isoformat(),
    }
    payload = {"username": bot_name, "embeds": [embed]}

    # 配信先URLを収集（全ユーザー + 固定チャンネル）。重複は除外し二重送信を防ぐ。
    urls = []
    seen = set()
    if users_df is not None and not users_df.empty:
        for _, row in users_df.iterrows():
            url = str(row.get('チャンネルURL', '')).strip()
            if url.startswith('http') and url not in seen:
                seen.add(url)
                urls.append(url)
    for url in EXTRA_ANNOUNCEMENT_WEBHOOKS:
        url = str(url).strip()
        if url.startswith('http') and url not in seen:
            seen.add(url)
            urls.append(url)

    for url in urls:
        if _post_announcement(url, payload):
            sent += 1
        else:
            failed += 1
    return sent, failed
