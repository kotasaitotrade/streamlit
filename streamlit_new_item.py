import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import hmac
import json
import time
import uuid
import requests
import pyotp
import qrcode
import io
import stripe
from PIL import Image
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError
import extra_streamlit_components as stx

st.set_page_config(page_title="ツウチマネージャー", layout="wide", page_icon="🜨")

from theme import apply_theme
apply_theme()

# ==========================================
#   設定・定数
# ==========================================
APP_BASE_URL = "https://discord-notify-tool.streamlit.app/"
CREDENTIALS_PATH = 'google_credentials.json'
TOKEN_PATH = 'gspread_token.json'
SPREADSHEET_ID = "1Y8VEVn95FOp5ELLtBiuUrB9m4S3qDSiX50G6aB88vnk"
TARGET_SHEET_NAME = "ユーザー設定"
USERS_SHEET_NAME = "ユーザー管理"
CHOICES_SHEET_NAME = "管理"
MACHINES = ["machine_1", "machine_2"]

OPTION_PRICE = 2000
PLANS = {
    "full": {
        "name": "プラン", "desc": "アパレル・その他の全てのカテゴリを選択可能", "type": "all",
        "base_price": 10000,
        "base_id": "price_1Tdgw1Ruq87ZH1sh4qTM8XlI",
        "opt_id": "price_1TdgvLRuq87ZH1sh6uoD4lCA",
        "base_plan_id": "plan_10000", "opt_plan_id": "plan_12000"
    },
}

# ==========================================
#   sedori ツール (メルカリ/ヤフフリ) クロスセル
#   feature flag: st.secrets.sedori.enabled or env ENABLE_SEDORI
#   - false (default) → 一切表示せず、既存ユーザーには見えない
#   - true            → プラン契約UIに「せどりツール」セクションが追加表示
# ==========================================
try:
    ENABLE_SEDORI = bool(st.secrets.get("sedori", {}).get("enabled", False))
except Exception:
    ENABLE_SEDORI = os.environ.get("ENABLE_SEDORI", "false").lower() == "true"

# Stripe price ID は本番作成後に Secrets で上書き可能
# (st.secrets.sedori.price_id_pricedown 等を最優先で参照する)
def _sec_price(key: str, default: str = "") -> str:
    try:
        return st.secrets.get("sedori", {}).get(key, default) or default
    except Exception:
        return default

SEDORI_PLANS = {
    "pricedown": {
        "name": "メルカリ/ヤフフリ 自動値下げ単品",
        "desc": "出品中の商品を時間帯ごとに自動値下げ。Discordで結果通知。",
        "price": 5000,
        "stripe_price_id": _sec_price("price_id_pricedown", "price_1Te5KnRuq87ZH1shI8MI1csP"),
        "plan_id": "plan_sedori_pricedown_5000",
        "allowed_tools": [3, 4],
    },
    "arrival": {
        "name": "メルカリ/ヤフフリ 新着通知単品",
        "desc": "メルカリ・ヤフフリの新着出品を即Discord通知。",
        "price": 5000,
        "stripe_price_id": _sec_price("price_id_arrival", "price_1Te5LVRuq87ZH1sh5SzpTxyc"),
        "plan_id": "plan_sedori_arrival_5000",
        "allowed_tools": [1, 2],
    },
    "all_full": {
        "name": "全部入り（EC + せどり）",
        "desc": "EC新着監視 + せどり全機能。プロ業者向け。",
        "price": 28000,
        "stripe_price_id": _sec_price("price_id_all_full", "price_1TedD7Ruq87ZH1shpjAAfF3T"),
        "plan_id": "plan_all_full_28000",
        "allowed_tools": [1, 2, 3, 4, 5],
    },
}

# 既存ユーザー含む全プラン表示用（ユーザー向けに「(旧)」表記なし）
PLAN_USER_LABEL = {
    "plan_10000": ("プラン", 10000),
    "plan_12000": ("プラン + キーワード通知オプション", 12000),
    "plan_9000":  ("プラン", 9000),
    "plan_11000": ("プラン + キーワード通知オプション", 11000),
    "plan_5000":  ("ライトプラン", 5000),
    "plan_7000":  ("ライトプラン + キーワード通知オプション", 7000),
}
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# 管理者アプリと共有する列定義（順番を変えないこと）
USER_COLS = [
    'ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'stripe_customer_id', 'subscription_id',
    'plan_id', 'チャンネルURL', 'plan', 'valid_until', 'assigned_machine', 'secret_key',
    'failed_count', 'locked_until', 'temp_plan_settings', 'role', 'joined_at',
    'assigned_sales', 'force_pw_change'
]

# ==========================================
#   Secrets & 認証処理
# ==========================================
try:
    DISCORD_BOT_TOKEN = st.secrets["discord"]["bot_token"]
    DISCORD_GUILD_ID = st.secrets["discord"]["guild_id"]
except:
    DISCORD_BOT_TOKEN = ""; DISCORD_GUILD_ID = ""
try:
    stripe.api_key = st.secrets["stripe"]["api_key"]
except:
    stripe.api_key = ""

def create_json_from_secrets():
    def recursive_dict(d):
        if hasattr(d, 'items'): return {k: recursive_dict(v) for k, v in d.items()}
        return d
    try:
        if "google_credentials" in st.secrets:
            with open(CREDENTIALS_PATH, "w") as f:
                f.write(json.dumps(recursive_dict(st.secrets["google_credentials"])))
        if "gspread_token" in st.secrets:
            with open(TOKEN_PATH, "w") as f:
                f.write(json.dumps(recursive_dict(st.secrets["gspread_token"])))
    except: pass

create_json_from_secrets()

def get_gspread_client():
    creds = None
    if os.path.exists(TOKEN_PATH):
        try: creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except: os.remove(TOKEN_PATH); creds = None
    if creds and creds.valid: return gspread.authorize(creds)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'w') as token: token.write(creds.to_json())
            return gspread.authorize(creds)
        except: creds = None
    return None

def show_tokushoho():
    st.markdown("---")
    with st.expander("⚖️ 特定商取引法に基づく表記", expanded=True):
        html_content = """
<style>
.tokushoho-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
.tokushoho-table th, .tokushoho-table td { border: 1px solid #ddd; padding: 12px; text-align: left; font-size: 14px; }
.tokushoho-table th { background-color: #f9f9f9; width: 30%; font-weight: bold; }
</style>
<table class="tokushoho-table">
<tr><th>販売業者</th><td>齋藤 航太</td></tr>
<tr><th>屋号 (ショップ名)</th><td>revolt shop</td></tr>
<tr><th>メールアドレス</th><td>koutaiwi@gmail.com</td></tr>
</table>
"""
        st.markdown(html_content, unsafe_allow_html=True)

# ==========================================
#   Discord & Stripe API Functions
# ==========================================
def create_discord_channel_and_webhook(user_discord_id, user_name):
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID: return False, "サーバー設定不足"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}
    url_create = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/channels"
    payload = {
        "name": f"通知-{user_discord_id}", "type": 0,
        "permission_overwrites": [
            {"id": DISCORD_GUILD_ID, "type": 0, "deny": "1024"},
            {"id": user_discord_id, "type": 1, "allow": "1024"}
        ]
    }
    res = requests.post(url_create, json=payload, headers=headers)
    if res.status_code not in [200, 201]: return False, f"作成失敗: {res.text}"
    channel_id = res.json()["id"]
    url_webhook = f"https://discord.com/api/v10/channels/{channel_id}/webhooks"
    res_wh = requests.post(url_webhook, json={"name": "新着通知Bot"}, headers=headers)
    if res_wh.status_code not in [200, 201]: return False, f"Webhook失敗: {res_wh.text}"
    return True, res_wh.json()["url"]

def create_stripe_checkout_session(user_id, price_id):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'], line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription', success_url=APP_BASE_URL + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=APP_BASE_URL, client_reference_id=str(user_id), metadata={'user_id': str(user_id)},
        )
        return True, session.url
    except Exception as e: return False, str(e)

def get_stripe_session_details(session_id):
    try: return stripe.checkout.Session.retrieve(session_id)
    except: return None

def cancel_stripe_subscription_at_period_end(subscription_id):
    try:
        stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        sub = stripe.Subscription.retrieve(subscription_id)
        return True, datetime.fromtimestamp(sub['current_period_end']).strftime('%Y/%m/%d')
    except Exception as e:
        if "No such subscription" in str(e): return True, "ALREADY_CANCELED"
        return False, str(e)

def change_stripe_subscription_plan(subscription_id, new_price_id):
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        item_id = sub['items']['data'][0].id
        stripe.Subscription.modify(subscription_id, items=[{'id': item_id, 'price': new_price_id}])
        return True, "プランを変更しました"
    except Exception as e: return False, str(e)

# ==========================================
#   セッションcookie (3時間ログイン維持)
# ==========================================
_SESSION_HOURS = 3
_COOKIE_NAME = "ntm_session"

def _cookie_secret():
    try:
        return str(st.secrets.get("cookie_secret", "ntm-default-secret-2026"))
    except Exception:
        return "ntm-default-secret-2026"

@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

def session_cookie_set(cookie_mgr, user_id, user_name):
    expiry = int(time.time()) + _SESSION_HOURS * 3600
    payload = f"{user_id}|{user_name}|{expiry}"
    sig = hmac.new(_cookie_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    cookie_mgr.set(_COOKIE_NAME, f"{payload}|{sig}",
                   expires_at=datetime.now() + timedelta(hours=_SESSION_HOURS))

def session_cookie_get(cookie_mgr):
    try:
        val = cookie_mgr.get(_COOKIE_NAME)
        if not val:
            return None, None
        *parts, sig = val.split("|")
        if len(parts) != 3:
            return None, None
        payload = "|".join(parts)
        expected = hmac.new(_cookie_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected):
            return None, None
        user_id, user_name, expiry = parts
        if int(time.time()) > int(expiry):
            return None, None
        return user_id, user_name
    except Exception:
        return None, None

def session_cookie_clear(cookie_mgr):
    try:
        cookie_mgr.delete(_COOKIE_NAME)
    except Exception:
        pass


# ==========================================
#   ユーザー管理・DB操作
# ==========================================
def hash_password(password): return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

@st.cache_data(ttl=60)
def get_users_df(_client):
    try:
        sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        data = sheet.get_all_values()
        if len(data) < 2: return pd.DataFrame(columns=USER_COLS)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        for c in USER_COLS:
            if c not in df.columns: df[c] = ""
        return df
    except: return pd.DataFrame(columns=USER_COLS)

def ensure_user_sheet_headers(client):
    """シートに不足している列ヘッダーを追記する（初回のみ実際に書き込みが走る）"""
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        headers = ws.row_values(1)
        new_headers = [c for c in USER_COLS if c not in headers]
        if new_headers:
            cols_to_add = (len(headers) + len(new_headers)) - ws.col_count
            if cols_to_add > 0:
                ws.add_cols(cols_to_add)
            for i, h in enumerate(new_headers):
                ws.update_cell(1, len(headers) + 1 + i, h)
            get_users_df.clear()
    except:
        pass

def _find_user_row_num(ws, user_id):
    """列1（ユーザーID列）のみ検索して行番号を返す"""
    try:
        col_values = ws.col_values(1)
        for i, val in enumerate(col_values):
            if val == str(user_id):
                return i + 1
        return None
    except:
        return None

def _update_user_field(client, user_id, col_name, value):
    """任意列をヘッダー名で指定して更新する"""
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        headers = ws.row_values(1)
        col_idx = headers.index(col_name) + 1 if col_name in headers else USER_COLS.index(col_name) + 1
        row_num = _find_user_row_num(ws, user_id)
        if row_num:
            ws.update_cell(row_num, col_idx, str(value))
            get_users_df.clear()
            return True
        return False
    except:
        return False

def login_user(client, login_input, password):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        row_num = _find_user_row_num(ws, login_input)
        if not row_num:
            # IDで見つからなければ名前でも探す
            name_col = ws.col_values(2)
            for i, val in enumerate(name_col):
                if val == str(login_input):
                    row_num = i + 1
                    break
        if not row_num:
            return False, "ユーザーIDまたはパスワードが間違っています", "", "", "", ""
        row_values = ws.row_values(row_num)
        while len(row_values) < len(USER_COLS):
            row_values.append("")
        if row_values[2] != hash_password(password):
            return False, "ユーザーIDまたはパスワードが間違っています", "", "", "", ""
        role = row_values[14] if row_values[14] else "user"
        if role == "disabled":
            return False, "このアカウントは無効化されています", "", "", "", ""
        force_pw = row_values[17]  # force_pw_change
        return True, "成功", row_values[0], row_values[1], row_values[10], force_pw
    except:
        return False, "ログイン処理エラー", "", "", "", ""

def register_user(client, user_id, user_name, password):
    get_users_df.clear()
    users_df = get_users_df(client)
    if str(user_id) in users_df['ユーザーID'].values: return False, "ID重複"
    if str(user_name) in users_df['ユーザー名'].values: return False, "名前重複"
    count_m1 = len(users_df[users_df['assigned_machine'] == MACHINES[0]])
    count_m2 = len(users_df[users_df['assigned_machine'] == MACHINES[1]])
    assigned_machine = MACHINES[0] if count_m1 <= count_m2 else MACHINES[1]

    try:
        with st.spinner("Discordチャンネルを作成中..."):
            suc, res = create_discord_channel_and_webhook(user_id, user_name)
            if not suc: return False, f"Discord作成失敗: {res}"
            webhook_url = res
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        # USER_COLS順に18列で登録
        sheet.append_row([
            str(user_id), str(user_name), hash_password(password), "", "", "",
            webhook_url, "", "", assigned_machine, "", "0", "", "",
            "user", "", "", ""
        ])
        get_users_df.clear()
        return True, "登録完了"
    except Exception as e: return False, f"エラー: {e}"

def update_user_temp_settings(client, user_id, restriction_type, plan_id):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell: ws.update_cell(cell.row, 14, f"{restriction_type},{plan_id}"); return True
        return False
    except: return False

def get_user_temp_settings(client, user_id):
    try:
        users_df = get_users_df(client)
        row = users_df[users_df['ユーザーID'] == str(user_id)]
        if not row.empty:
            parts = str(row.iloc[0].get('temp_plan_settings', 'all,plan_10000')).split(',')
            if len(parts) >= 2: return parts[0], parts[1]
        return 'all', 'plan_10000'
    except: return 'all', 'plan_10000'

def update_user_stripe_data(client, user_id, stripe_id=None, subscription_id=None, plan_id=None, restriction_type=None, valid_until=None):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            if stripe_id is not None: ws.update_cell(cell.row, 4, stripe_id)
            if subscription_id is not None: ws.update_cell(cell.row, 5, subscription_id)
            if plan_id is not None: ws.update_cell(cell.row, 6, plan_id)
            if restriction_type is not None: ws.update_cell(cell.row, 8, restriction_type)
            if valid_until is not None: ws.update_cell(cell.row, 9, valid_until)
            get_users_df.clear()
            return True
    except: return False

# ==========================================
#   通知設定用 (新マトリクスUI)
# ==========================================
@st.cache_data(ttl=15)
def get_choices_df(_client):
    try:
        data = _client.open_by_key(SPREADSHEET_ID).worksheet(CHOICES_SHEET_NAME).get_all_values()
        if len(data) < 2: return pd.DataFrame(columns=['サイト', 'カテゴリ', 'チャンネル'])
        return pd.DataFrame(data[1:], columns=[str(h).strip() for h in data[0]]).astype(str)
    except: return pd.DataFrame(columns=['サイト', 'カテゴリ', 'チャンネル'])

@st.cache_data(ttl=60)
def load_data(_client):
    try:
        data = _client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME).get_all_values()
        final_cols = ['ユーザーID', '検索条件', 'キーワード']
        if not data: return pd.DataFrame(columns=final_cols)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        if 'ブランドキーワード' in df.columns and 'キーワード' not in df.columns: df['キーワード'] = df['ブランドキーワード']
        for col in final_cols:
            if col not in df.columns: df[col] = ""
        return df[final_cols]
    except: return None

def get_allowed_options(client, restriction_type):
    choices_df = get_choices_df(client)
    allowed = []
    for _, row in choices_df.drop_duplicates().iterrows():
        site, cat, kind = str(row.get('サイト', '')).strip(), str(row.get('カテゴリ', '')).strip(), str(row.get('チャンネル', '')).replace(' ', '').strip()
        if not site: continue
        combo = f"{site} - {cat}"
        i_type = 'apparel' if kind == 'アパレル' else ('not_apparel' if kind == 'アパレル以外' else 'other')
        if restriction_type == 'all' or (restriction_type == 'apparel' and i_type == 'apparel') or (restriction_type == 'not_apparel' and i_type == 'not_apparel'):
            allowed.append(combo)
    return sorted(list(set(allowed)))

# ★ 修正: カンマ区切りの文字列を、横の列（OR条件）に動的に展開
def expand_keywords_to_dataframe(user_df):
    max_cols = st.session_state.get('kw_col_count', 3)
    expanded_rows = []
    
    for _, row in user_df.iterrows():
        combo = str(row.get('検索条件', '')).strip()
        kw_str = str(row.get('キーワード', '')).strip()
        
        if not kw_str or kw_str.lower() in ['none', 'nan', '(データなし)']:
            expanded_rows.append({'検索条件': combo})
            continue
            
        # カンマ区切りでOR条件のリストを取得
        or_items = [g.strip() for g in kw_str.replace('、', ',').split(',') if g.strip()]
        
        # 既存データが現在の列数より多ければ、自動で列数を増やす
        if len(or_items) > max_cols:
            max_cols = len(or_items)
            
        new_row = {'検索条件': combo}
        # 横の列に順番に割り当てる
        for i in range(len(or_items)):
            new_row[f'キーワード{i+1}'] = or_items[i]
            
        expanded_rows.append(new_row)
            
    st.session_state['kw_col_count'] = max_cols
    
    if not expanded_rows:
        return pd.DataFrame(columns=['検索条件'] + [f'キーワード{i+1}' for i in range(max_cols)])
        
    df = pd.DataFrame(expanded_rows)
    for i in range(max_cols):
        col_name = f'キーワード{i+1}'
        if col_name not in df.columns: df[col_name] = ""
            
    cols = ['検索条件'] + [f'キーワード{i+1}' for i in range(max_cols)]
    return df[cols]

# ★ 修正: UIの各列をカンマで繋いで保存
def add_initial_notification_settings(client, user_id, restriction_type):
    """決済完了後にプランに応じた初期通知設定を追加する"""
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        data = sheet.get_all_values()
        if data and len(data) > 1:
            df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        else:
            df = pd.DataFrame(columns=['ユーザーID', '検索条件', 'キーワード'])
        for c in ['ユーザーID', '検索条件', 'キーワード']:
            if c not in df.columns: df[c] = ""

        if str(user_id) in df['ユーザーID'].values:
            return  # 既に設定あり → スキップ

        new_rows = []
        if restriction_type in ['all', 'apparel']:
            new_rows.append({'ユーザーID': str(user_id), '検索条件': 'セカスト - バッグ', 'キーワード': ''})
        if restriction_type in ['all', 'not_apparel']:
            new_rows.append({'ユーザーID': str(user_id), '検索条件': 'オフモール - カメラ', 'キーワード': ''})

        if not new_rows:
            return
        final_df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        sheet.clear()
        sheet.update('A1', [final_df.columns.tolist()] + final_df.astype(str).values.tolist())
        load_data.clear()
    except Exception:
        pass  # 初期設定失敗は致命的でないため無視

def save_merged_data(client, full_df, edited_df, user_id, restriction_type):
    try:
        allowed_opts = get_allowed_options(client, restriction_type)
        result_dict = {}
        
        for _, row in edited_df.iterrows():
            combo = str(row.get('検索条件', '')).strip()
            if not combo or combo in ["", "None", "nan", "NaN", "(データなし)"]: continue
            if combo not in allowed_opts:
                st.error(f"保存失敗: 「{combo}」は現在のプラン設定では選択できません。")
                return None
                
            or_items = []
            for i in range(st.session_state['kw_col_count']):
                val = str(row.get(f'キーワード{i+1}', '')).strip()
                if val and val.lower() not in ["none", "nan"]:
                    # DBフォーマット上、カンマは枠の区切り(OR)として使うため、枠内のカンマはスペース(AND)に置換
                    clean_val = val.replace(',', ' ').replace('、', ' ')
                    # 連続するスペースを1つに整形
                    clean_val = ' '.join(clean_val.split())
                    if clean_val: or_items.append(clean_val)
            
            if or_items:
                or_str = ', '.join(or_items)
                if combo not in result_dict: result_dict[combo] = []
                result_dict[combo].append(or_str)
            else:
                if combo not in result_dict: result_dict[combo] = []
                
        new_rows = []
        for combo, or_lists in result_dict.items():
            # 複数行に同じ検索条件があった場合、それらもまとめてカンマで繋ぐ
            combined_or_list = [item for sublist in or_lists for item in sublist.split(', ')]
            
            if len(combined_or_list) > 30:
                st.error(f"エラー: 「{combo}」のキーワード枠が多すぎます（最大30枠まで）")
                return None
                
            kw_str = ', '.join(combined_or_list)
            new_rows.append({'ユーザーID': str(user_id), '検索条件': combo, 'キーワード': kw_str})
            
        save_user_df = pd.DataFrame(new_rows)
        other_users_df = full_df[full_df['ユーザーID'] != str(user_id)]
        for c in ['ユーザーID', '検索条件', 'キーワード']:
            if c not in save_user_df.columns: save_user_df[c] = ""
            if c not in other_users_df.columns: other_users_df[c] = ""
            
        final_df = pd.concat([other_users_df, save_user_df], ignore_index=True)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        sheet.clear()
        sheet.update('A1', [final_df.columns.tolist()] + final_df.astype(str).values.tolist())
        load_data.clear()
        st.success(f"✅ 設定保存完了")
        return final_df
    except Exception as e: st.error(f"保存エラー: {e}"); return None

# ==========================================
#   メイン
# ==========================================
def main():
    client = get_gspread_client()
    if not client: return

    if "session_id" in st.query_params:
        session = get_stripe_session_details(st.query_params["session_id"])
        if session and session.payment_status == 'paid':
            metadata = getattr(session, 'metadata', None) or {}
            target_uid = metadata.get('user_id') if isinstance(metadata, dict) else getattr(metadata, 'user_id', None)
            if target_uid:
                saved_restriction, saved_plan_id = get_user_temp_settings(client, target_uid)
                update_user_stripe_data(client, target_uid, stripe_id=session.customer, subscription_id=session.subscription, plan_id=saved_plan_id, restriction_type=saved_restriction, valid_until="")
                add_initial_notification_settings(client, target_uid, saved_restriction)
                st.success("🎉 お支払いが完了しました！"); time.sleep(3); st.query_params.clear()
                st.session_state['logged_in_user_id'] = target_uid
                cookie_mgr = get_cookie_manager()
                session_cookie_set(cookie_mgr, target_uid, target_uid)
                st.rerun()
        st.stop()

    ensure_user_sheet_headers(client)

    cookie_mgr = get_cookie_manager()

    if 'logged_in_user_id' not in st.session_state: st.session_state['logged_in_user_id'] = None
    if 'force_pw_change' not in st.session_state: st.session_state['force_pw_change'] = False

    # cookieから自動ログイン復元
    if st.session_state['logged_in_user_id'] is None:
        uid_c, uname_c = session_cookie_get(cookie_mgr)
        if uid_c:
            st.session_state['logged_in_user_id'] = uid_c
            st.session_state['logged_in_user_name'] = uname_c

    if st.session_state['logged_in_user_id'] is None:
        st.markdown("## 📊 ツウチマネージャー (市場リサーチツール)")
        tab1, tab2 = st.tabs(["🔑 ログイン", "✨ 新規登録"])
        with tab1:
            li = st.text_input("ID / 名前", key="li")
            lp = st.text_input("パスワード", type="password", key="lp")
            if st.button("ログイン", type="primary"):
                suc, msg, uid, uname, _, force_pw = login_user(client, li, lp)
                if suc:
                    st.session_state['logged_in_user_id'] = uid
                    st.session_state['logged_in_user_name'] = uname
                    st.session_state['force_pw_change'] = (force_pw == "1")
                    session_cookie_set(cookie_mgr, uid, uname)
                    st.rerun()
                else: st.error(msg)
        with tab2:
            st.markdown(f"""
**💴 料金プラン**

| プラン | 月額 |
|---|---|
| プラン | **¥{PLANS['full']['base_price']:,}/月** |
| + キーワード通知オプション | **+¥{OPTION_PRICE:,}/月** |

※ 登録は無料です。プラン契約はログイン後に「プラン契約・解約」メニューから行えます。
※ いつでも解約可能、契約期間終了日までサービスをご利用いただけます。
""")
            st.divider()
            ri, rn, rp = st.text_input("Discord ID", key="ri"), st.text_input("表示名", key="rn"), st.text_input("パスワード", type="password", key="rp")
            if st.button("登録"):
                if not ri or not rn or not rp: st.error("入力不足")
                else:
                    suc, msg = register_user(client, ri, rn, rp)
                    if suc: st.success(msg); st.balloons()
                    else: st.error(msg)
        show_tokushoho()
        st.stop()

    # パスワード強制変更が必要な場合
    if st.session_state.get('force_pw_change'):
        uid_tmp = st.session_state['logged_in_user_id']
        st.title("🔐 パスワードの変更が必要です")
        st.warning("管理者によってパスワードの変更が要求されています。新しいパスワードを設定してください。")
        with st.form("force_pw_form"):
            new_pw = st.text_input("新しいパスワード", type="password")
            confirm_pw = st.text_input("確認（再入力）", type="password")
            submitted = st.form_submit_button("パスワードを変更する", type="primary")
        if submitted:
            if not new_pw or not confirm_pw: st.error("パスワードを入力してください")
            elif new_pw != confirm_pw: st.error("パスワードが一致しません")
            elif len(new_pw) < 6: st.error("パスワードは6文字以上で設定してください")
            else:
                _update_user_field(client, uid_tmp, 'パスワードハッシュ', hash_password(new_pw))
                _update_user_field(client, uid_tmp, 'force_pw_change', "")
                st.success("パスワードを変更しました")
                st.session_state['force_pw_change'] = False
                time.sleep(1.5)
                st.rerun()
        st.stop()

    uid = st.session_state['logged_in_user_id']
    users_df = get_users_df(client)
    user_row = users_df[users_df['ユーザーID'] == str(uid)].iloc[0]
    
    sub_id = str(user_row.get('subscription_id', ''))
    current_plan_id = str(user_row.get('plan_id', ''))
    restriction_type = str(user_row.get('plan', 'all'))
    
    valid_until_str = str(user_row.get('valid_until', ''))
    is_period_active = False
    if valid_until_str:
        try:
            if datetime.now(timezone(timedelta(hours=9))).date() <= datetime.strptime(valid_until_str.split(' ')[0], '%Y/%m/%d').date(): is_period_active = True
        except: pass

    has_active_sub = (sub_id != "" and sub_id.lower() not in ["nan", "none"])
    is_access_allowed = has_active_sub or is_period_active
    has_option = current_plan_id in ["plan_12000", "plan_11000", "plan_7000"]

    with st.sidebar:
        st.write(f"User: **{st.session_state.get('logged_in_user_name','')}**")
        menu = st.radio("メニュー", ["通知設定", "プラン契約・解約", "アカウント設定"])
        if st.button("ログアウト"):
            session_cookie_clear(cookie_mgr)
            st.session_state['logged_in_user_id'] = None
            st.rerun()

    full_df = load_data(client)

    if menu == "通知設定":
        st.subheader("📢 通知条件の設定")
        if not is_access_allowed: st.error("プラン契約が必要です"); st.stop()

        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        allowed_opts = get_allowed_options(client, restriction_type)

        settings_key = f'settings_{uid}'
        if settings_key not in st.session_state:
            rows = []
            for _, row in user_df.iterrows():
                combo = str(row.get('検索条件', '')).strip()
                kw_str = str(row.get('キーワード', '')).strip()
                if kw_str.lower() in ['none', 'nan']: kw_str = ''
                if combo not in allowed_opts: combo = ''
                row_id = uuid.uuid4().hex[:8]
                rows.append(row_id)
                st.session_state[f'combo_{row_id}'] = combo
                st.session_state[f'kw_{row_id}'] = kw_str
            if not rows:
                row_id = uuid.uuid4().hex[:8]
                rows.append(row_id)
                st.session_state[f'combo_{row_id}'] = ''
                st.session_state[f'kw_{row_id}'] = ''
            st.session_state[settings_key] = rows

        current_rows = st.session_state[settings_key]

        if has_option:
            st.success("✅ **キーワード通知オプション: 有効**")
            st.info("💡 OR条件はカンマ区切り `ナイキ 黒, アディダス`　AND条件はスペース区切り `ナイキ 黒`")
        else:
            st.warning("🔒 **キーワード通知オプション: 無効**")

        rows_to_delete = []
        for row_id in current_rows:
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                with col1:
                    val = st.session_state.get(f'combo_{row_id}', '')
                    idx = (allowed_opts.index(val) + 1) if val in allowed_opts else 0
                    st.selectbox("検索条件", [''] + allowed_opts, index=idx, key=f'combo_{row_id}')
                with col2:
                    st.write("")
                    if st.button("🗑️", key=f'del_{row_id}'):
                        rows_to_delete.append(row_id)
                if has_option:
                    st.text_input("キーワード（OR: カンマ区切り / AND: スペース区切り）",
                        key=f'kw_{row_id}',
                        placeholder="例: ナイキ 黒, アディダス")

        if rows_to_delete:
            for row_id in rows_to_delete:
                current_rows.remove(row_id)
            st.session_state[settings_key] = current_rows
            st.rerun()

        col_add, col_save = st.columns([1, 1])
        with col_add:
            if st.button("➕ 検索条件を追加"):
                row_id = uuid.uuid4().hex[:8]
                current_rows.append(row_id)
                st.session_state[f'combo_{row_id}'] = ''
                st.session_state[f'kw_{row_id}'] = ''
                st.session_state[settings_key] = current_rows
                st.rerun()
        with col_save:
            if st.button("💾 設定を保存", type="primary"):
                save_ok = True
                save_rows = []
                for row_id in current_rows:
                    combo = st.session_state.get(f'combo_{row_id}', '').strip()
                    if not combo or combo in ["None", "nan", "NaN"]: continue
                    if combo not in allowed_opts:
                        st.error(f"保存失敗: 「{combo}」は現在のプラン設定では選択できません。"); save_ok = False; break
                    kw_str = st.session_state.get(f'kw_{row_id}', '').strip()
                    if kw_str.lower() in ['none', 'nan']: kw_str = ''
                    if not has_option: kw_str = ''
                    save_rows.append({'ユーザーID': str(uid), '検索条件': combo, 'キーワード': kw_str})
                if save_ok:
                    try:
                        save_df = pd.DataFrame(save_rows) if save_rows else pd.DataFrame(columns=['ユーザーID', '検索条件', 'キーワード'])
                        other_df = full_df[full_df['ユーザーID'] != str(uid)] if full_df is not None else pd.DataFrame(columns=['ユーザーID', '検索条件', 'キーワード'])
                        for c in ['ユーザーID', '検索条件', 'キーワード']:
                            if c not in save_df.columns: save_df[c] = ""
                            if c not in other_df.columns: other_df[c] = ""
                        final_df = pd.concat([other_df, save_df], ignore_index=True)
                        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
                        sheet.clear()
                        sheet.update('A1', [final_df.columns.tolist()] + final_df.astype(str).values.tolist())
                        load_data.clear()
                        del st.session_state[settings_key]
                        st.success("✅ 設定保存完了")
                    except Exception as e: st.error(f"保存エラー: {e}")

    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        if has_active_sub:
            # 現在のプラン情報を表示
            plan_label, plan_price = PLAN_USER_LABEL.get(current_plan_id, ("プラン", 0))
            if plan_price > 0:
                st.success(f"✅ **現在プラン契約中**")
                pc1, pc2 = st.columns(2)
                pc1.metric("ご契約プラン", plan_label)
                pc2.metric("月額", f"¥{plan_price:,}")
            else:
                st.success("✅ **現在プラン契約中です**")
            st.caption("💡 解約しても契約期間終了日までサービスは継続してご利用いただけます。")
            if st.button("プランを解約する"):
                suc, msg = cancel_stripe_subscription_at_period_end(sub_id)
                if suc: update_user_stripe_data(client, uid, subscription_id="", valid_until=datetime.now().strftime('%Y/%m/%d') if msg == "ALREADY_CANCELED" else msg); st.rerun()

            # --- sedori クロスセル (既存契約中ユーザー向け) ---
            if ENABLE_SEDORI:
                st.divider()
                st.markdown("### 🛒 せどりツールも追加できます")
                st.markdown(
                    "**メルカリ / ヤフフリ専用のせどり業務効率化ツール** を別途追加でご利用いただけます。\n\n"
                    "- 📉 **自動値下げ**：出品中の商品を3時間ごとに自動値下げ。希少品やいいね無反応特例も搭載\n"
                    "- 🔍 **新着通知**：指定の型番・キーワードでメルカリ/ヤフフリの新着商品をDiscord即通知\n"
                    "- 🤝 **連携活用**：EC新着で見つけた商品の市場価格をメルカリでチェック→自動値下げ出品まで一気通貫"
                )
                up_col1, up_col2, up_col3 = st.columns(3)
                for col, key in zip([up_col1, up_col2, up_col3], ["pricedown", "arrival", "all_full"]):
                    p = SEDORI_PLANS[key]
                    with col:
                        st.markdown(f"**{p['name']}**")
                        st.caption(p["desc"])
                        st.metric("月額（追加分）", f"¥{p['price']:,}")
                        if st.button(f"このプランを追加", key=f"upsell_{key}"):
                            suc, url = create_stripe_checkout_session(uid, p["stripe_price_id"])
                            if suc:
                                st.link_button("お支払い画面へ進む", url, type="primary")
                            else:
                                st.error(f"Stripe 初期化エラー: {url}")
                st.caption("💡 追加プランは現在のサブスクとは別契約になります。両方解約したい場合は順に解約してください。")
        else:
            plan_key = "full"
            st.info(f"**プラン** ¥{PLANS[plan_key]['base_price']:,}/月")
            light_restriction = "all"
            use_option = st.checkbox(f"✨ キーワード通知オプションを追加 (+¥{OPTION_PRICE:,})")
            target_price_id = PLANS[plan_key]['opt_id'] if use_option else PLANS[plan_key]['base_id']
            target_plan_str = PLANS[plan_key]['opt_plan_id'] if use_option else PLANS[plan_key]['base_plan_id']

            st.divider()
            st.markdown("#### 📋 利用規約")
            st.markdown("""
<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:16px;font-size:0.85rem;line-height:1.7;max-height:220px;overflow-y:auto;">

**第1条（サービスの性質）**
本サービスは、フリマ・オークションサイトの新着商品情報をDiscordへ通知するツールです。通知はリアルタイムを目指していますが、確実な配信を保証するものではありません。

**第2条（サービスの中断・停止）**
サーバーメンテナンス、障害、外部APIの仕様変更、その他やむを得ない事情により、予告なく通知が遅延・停止する場合があります。これらによって生じた損害について、運営は一切の責任を負いません。

**第3条（免責事項）**
本サービスの利用により生じた商機の逸失・損失・損害（通知の未着・遅延・誤通知を含む）について、運営は一切の責任を負いません。商品の購入判断はユーザー自身の責任において行ってください。

**第4条（料金・解約）**
月額料金は前払い制です。解約は「プラン契約・解約」メニューからいつでも行えます。解約後も契約期間終了まではサービスをご利用いただけます。日割り返金には対応しておりません。

**第5条（禁止事項）**
アカウントの第三者への譲渡・共有、サービスの不正利用、リバースエンジニアリング等を禁止します。違反が認められた場合、予告なくアカウントを停止することがあります。

**第6条（規約の変更）**
運営は本規約を予告なく変更する場合があります。変更後もサービスを継続利用した場合、新規約に同意したものとみなします。

</div>
""", unsafe_allow_html=True)
            agree = st.checkbox("上記の利用規約を読み、同意します")
            if st.button("お支払い画面へ進む", disabled=not agree):
                update_user_temp_settings(client, uid, light_restriction, target_plan_str)
                suc, url = create_stripe_checkout_session(uid, target_price_id)
                if suc: st.link_button("支払いを完了させる", url, type="primary")

    elif menu == "アカウント設定":
        st.subheader("⚙️ アカウント設定")
        st.write("#### パスワード変更")
        with st.form("self_pw_form"):
            current_pw = st.text_input("現在のパスワード", type="password")
            new_pw = st.text_input("新しいパスワード", type="password")
            confirm_pw = st.text_input("確認（再入力）", type="password")
            submitted = st.form_submit_button("パスワードを変更する")
        if submitted:
            if not current_pw or not new_pw or not confirm_pw:
                st.error("全項目を入力してください")
            elif new_pw != confirm_pw:
                st.error("新しいパスワードが一致しません")
            elif len(new_pw) < 6:
                st.error("パスワードは6文字以上で設定してください")
            else:
                try:
                    ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
                    row_num = _find_user_row_num(ws, uid)
                    if not row_num: st.error("ユーザーが見つかりません")
                    elif ws.row_values(row_num)[2] != hash_password(current_pw): st.error("現在のパスワードが違います")
                    else:
                        _update_user_field(client, uid, 'パスワードハッシュ', hash_password(new_pw))
                        st.success("パスワードを変更しました")
                except Exception as e: st.error(f"エラー: {e}")

if __name__ == "__main__":
    main()
