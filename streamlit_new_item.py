import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import json
import time
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

# ★ st.set_page_config は最初に呼び出す必要があります
st.set_page_config(page_title="通知設定マネージャー", layout="wide")

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

# ★ プラン設定 (StripeのPrice IDを設定)
OPTION_PRICE = 2000
PLANS = {
    "full": {
        "name": "フルプラン (全て)",
        "desc": "アパレル・その他の全てのカテゴリを選択可能",
        "type": "all",
        "base_price": 9000,
        "base_id": "price_1T0D0LRp7tXAl48PFa7JBztW",            # フルプラン単体
        "opt_id": "price_1T0D1yRp7tXAl48P0ep6L76Y"             # フルプラン+OP
    },
    "light": {
        "name": "ライトプラン (片方のみ)",
        "desc": "「アパレル」または「それ以外」のどちらか一方のみ選択可能",
        "type": "select",
        "base_price": 5000,
        "base_id": "price_1T0CetRp7tXAl48PCcvLKVJ6",           # ライトプラン単体
        "opt_id": "price_1T0CjERp7tXAl48PLckXXhG4"            # ライトプラン+OP
    }
}

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# ==========================================
#   Secrets & 認証処理
# ==========================================
try:
    DISCORD_BOT_TOKEN = st.secrets["discord"]["bot_token"]
    DISCORD_GUILD_ID = st.secrets["discord"]["guild_id"]
except Exception as e:
    DISCORD_BOT_TOKEN = ""
    DISCORD_GUILD_ID = ""
    st.error(f"⚠️ Discord Secrets読み込みエラー: {e}")

try:
    stripe.api_key = st.secrets["stripe"]["api_key"]
except Exception as e:
    stripe.api_key = ""
    st.error(f"⚠️ Stripe Secrets読み込みエラー: {e}")

def create_json_from_secrets():
    def recursive_dict(d):
        if hasattr(d, 'items'):
            return {k: recursive_dict(v) for k, v in d.items()}
        return d
    try:
        if "google_credentials" in st.secrets:
            with open(CREDENTIALS_PATH, "w") as f:
                creds_dict = recursive_dict(st.secrets["google_credentials"])
                f.write(json.dumps(creds_dict))
        if "gspread_token" in st.secrets:
            with open(TOKEN_PATH, "w") as f:
                token_dict = recursive_dict(st.secrets["gspread_token"])
                f.write(json.dumps(token_dict))
    except Exception as e:
        st.error(f"⚠️ Google Secrets読み込みエラー: {e}")

create_json_from_secrets()

def get_gspread_client():
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            os.remove(TOKEN_PATH)
            creds = None
    if creds and creds.valid:
        return gspread.authorize(creds)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'w') as token:
                token.write(creds.to_json())
            return gspread.authorize(creds)
        except Exception:
            creds = None
    if not os.path.exists(CREDENTIALS_PATH):
        st.error("認証ファイルが見つかりません。")
        return None
    return None

def show_tokushoho():
    st.markdown("---")
    with st.expander("⚖️ 特定商取引法に基づく表記", expanded=True):
        st.markdown("""
        | 項目 | 内容 |
        | :--- | :--- |
        | **販売業者** | 齋藤 航太 |
        | **代表責任者** | 齋藤 航太 |
        | **所在地** | 〒156-0055 東京都世田谷区船橋2-8-1 |
        | **電話番号** | 080-3423-1798 |
        | **メールアドレス** | koutaiwi@gmail.com |
        | **販売価格** | 本ページ上部の「料金プラン」に記載 |
        | **支払方法** | クレジットカード決済 (Stripe) |
        """)

# ==========================================
#   Discord API連携
# ==========================================
def create_discord_channel_and_webhook(user_discord_id, user_name):
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        return False, "サーバー設定不足"

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url_create = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/channels"
    payload = {
        "name": f"通知-{user_name}",
        "type": 0,
        "permission_overwrites": [
            {"id": DISCORD_GUILD_ID, "type": 0, "deny": "1024"},
            {"id": user_discord_id, "type": 1, "allow": "1024"}
        ]
    }
    
    res = requests.post(url_create, json=payload, headers=headers)
    if res.status_code not in [200, 201]: return False, f"チャンネル作成失敗: {res.text}"
    
    channel_data = res.json()
    channel_id = channel_data["id"]

    url_webhook = f"https://discord.com/api/v10/channels/{channel_id}/webhooks"
    webhook_payload = {"name": "新着通知Bot"}
    res_wh = requests.post(url_webhook, json=webhook_payload, headers=headers)
    if res_wh.status_code not in [200, 201]: return False, f"Webhook作成失敗: {res_wh.text}"
        
    webhook_data = res_wh.json()
    return True, webhook_data["url"]

# ==========================================
#   Stripe API Functions
# ==========================================
def create_stripe_checkout_session(user_id, price_id):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=APP_BASE_URL + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=APP_BASE_URL,
            client_reference_id=str(user_id),
            metadata={'user_id': str(user_id)},
        )
        return True, checkout_session.url
    except Exception as e:
        return False, str(e)

def get_stripe_session_details(session_id):
    try: return stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        st.error(f"Stripe Session取得エラー: {e}")
        return None

def cancel_stripe_subscription_at_period_end(subscription_id):
    try:
        stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        sub = stripe.Subscription.retrieve(subscription_id)
        current_period_end = sub['current_period_end']
        end_date = datetime.fromtimestamp(current_period_end)
        return True, end_date.strftime('%Y/%m/%d')
    except Exception as e:
        # ▼修正: Stripe側に契約がない場合（手動削除など）は、すでに解約されたものとして扱う
        if "No such subscription" in str(e):
            return True, "ALREADY_CANCELED"
        return False, str(e)

def change_stripe_subscription_plan(subscription_id, new_price_id):
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        item_id = sub['items']['data'][0].id
        stripe.Subscription.modify(subscription_id, items=[{'id': item_id, 'price': new_price_id}])
        return True, "プランを変更しました"
    except Exception as e:
        # ▼修正: Stripe側に契約がない場合
        if "No such subscription" in str(e):
            return False, "Stripe上に有効な契約が見つかりません。一度解約ボタンを押してシステムをリセットし、再度契約してください。"
        return False, str(e)

# ==========================================
#   ユーザー管理・DB操作
# ==========================================
def hash_password(password):
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def ensure_users_sheet(client):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        expected_headers = [
            'ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'stripe_customer_id', 
            'subscription_id', 'plan_id', 'チャンネルURL', 'plan', 'valid_until', 
            'assigned_machine', 'secret_key', 'failed_count', 'locked_until', 'temp_plan_settings'
        ]
        try: ws = sh.worksheet(USERS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=14)
            ws.append_row(expected_headers)
            return

        if ws.col_count < 14: ws.resize(cols=14)
        headers = ws.row_values(1)
        needs_update = False
        if len(headers) < 14:
            headers += [""] * (14 - len(headers))
            needs_update = True
        
        for i, h in enumerate(expected_headers):
            if i < len(headers):
                if headers[i] == "" or (i == 3 and "fincode" in headers[i]):
                    headers[i] = h
                    needs_update = True
        
        if needs_update: ws.update('A1:N1', [headers])
    except Exception as e:
        st.error(f"ユーザーDB初期化エラー: {e}")

@st.cache_data(ttl=60)
def get_users_df(_client):
    max_retries = 3
    for i in range(max_retries):
        try:
            sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
            data = sheet.get_all_values()
            cols = [
                'ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'stripe_customer_id', 
                'subscription_id', 'plan_id', 'チャンネルURL', 'plan', 'valid_until', 
                'assigned_machine', 'secret_key', 'failed_count', 'locked_until', 'temp_plan_settings'
            ]
            if len(data) < 2: return pd.DataFrame(columns=cols)
            df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
            if 'fincode_customer_id' in df.columns: df = df.rename(columns={'fincode_customer_id': 'stripe_customer_id'})
            for c in cols:
                if c not in df.columns: df[c] = ""
            return df
        except APIError as e:
            if "429" in str(e) and i < max_retries - 1:
                time.sleep(2 ** i)
                continue
            return pd.DataFrame()
        except Exception: return pd.DataFrame()

def register_user(client, user_id, user_name, password):
    get_users_df.clear()
    users_df = get_users_df(client)
    if str(user_id) in users_df['ユーザーID'].values: return False, "ID重複"
    if str(user_name) in users_df['ユーザー名'].values: return False, "名前重複"
        
    count_m1 = len(users_df[users_df['assigned_machine'] == MACHINES[0]])
    count_m2 = len(users_df[users_df['assigned_machine'] == MACHINES[1]])
    assigned_machine = MACHINES[0] if count_m1 <= count_m2 else MACHINES[1]

    webhook_url = ""
    try:
        with st.spinner("Discordチャンネルを作成中..."):
            suc, res = create_discord_channel_and_webhook(user_id, user_name)
            if suc: webhook_url = res
            else: return False, f"Discord作成失敗: {res}"
    except Exception as e: return False, f"Discordエラー: {e}"

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        hashed_pw = hash_password(password)
        sheet.append_row([str(user_id), str(user_name), hashed_pw, "", "", "", webhook_url, "", "", assigned_machine, "", "0", "", ""])
        get_users_df.clear()
        return True, "登録完了"
    except Exception as e: return False, f"保存エラー: {e}"

def login_user(client, login_input, password):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(login_input))
        if not cell: return False, "ユーザーIDまたはパスワードが間違っています", "", "", ""
        
        row_values = ws.row_values(cell.row)
        if len(row_values) < 14: row_values += [""] * (14 - len(row_values))
            
        user_id = row_values[0]
        user_name = row_values[1]
        stored_hash = row_values[2]
        secret_key = row_values[10]
        failed_count_str = row_values[11]
        locked_until_str = row_values[12]

        JST = timezone(timedelta(hours=9))
        now = datetime.now(JST)
        
        if locked_until_str:
            try:
                lock_time = datetime.strptime(locked_until_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=JST)
                if now < lock_time:
                    remain = int((lock_time - now).total_seconds() / 60)
                    return False, f"アカウントはロックされています。約{remain}分後にお試しください。", "", "", ""
            except: pass
        
        if stored_hash == hash_password(password):
            if failed_count_str != "0" or locked_until_str != "":
                ws.update_cell(cell.row, 12, "0")
                ws.update_cell(cell.row, 13, "")
            return True, "成功", user_id, user_name, secret_key
        else:
            current_fail = int(failed_count_str) if failed_count_str.isdigit() else 0
            new_fail = current_fail + 1
            ws.update_cell(cell.row, 12, str(new_fail))
            if new_fail >= 10:
                lock_until = now + timedelta(minutes=30)
                ws.update_cell(cell.row, 13, lock_until.strftime('%Y-%m-%d %H:%M:%S'))
                return False, "連続失敗のためアカウントを一時的にロックしました（30分間）。", "", "", ""
            return False, "ユーザーIDまたはパスワードが間違っています", "", "", ""
    except Exception as e: return False, f"ログイン処理エラー: {e}", "", "", ""

def update_user_password(client, user_id, new_password):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            ws.update_cell(cell.row, 3, hash_password(new_password))
            get_users_df.clear()
            return True, "パスワードを変更しました"
        return False, "ユーザーが見つかりません"
    except Exception as e: return False, f"更新エラー: {e}"

def update_user_secret(client, user_id, secret_key):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            ws.update_cell(cell.row, 11, secret_key)
            get_users_df.clear()
            return True
        return False
    except: return False

def update_user_temp_settings(client, user_id, restriction_type, plan_id):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            ws.update_cell(cell.row, 14, f"{restriction_type},{plan_id}")
            return True
        return False
    except: return False

def get_user_temp_settings(client, user_id):
    try:
        users_df = get_users_df(client)
        row = users_df[users_df['ユーザーID'] == str(user_id)]
        if not row.empty:
            parts = str(row.iloc[0].get('temp_plan_settings', 'all,plan_9000')).split(',')
            if len(parts) >= 2: return parts[0], parts[1]
        return 'all', 'plan_9000'
    except: return 'all', 'plan_9000'

def update_user_stripe_data(client, user_id, stripe_id=None, subscription_id=None, plan_id=None, restriction_type=None, valid_until=None):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            if stripe_id is not None: ws.update_cell(cell.row, 4, stripe_id)
            if subscription_id is not None: ws.update_cell(cell.row, 5, subscription_id)
            if plan_id is not None: ws.update_cell(cell.row, 6, plan_id)
            if restriction_type is not None: ws.update_cell(cell.row, 8, restriction_type)
            if valid_until is not None: ws.update_cell(cell.row, 9, valid_until)
            get_users_df.clear()
            return True
    except Exception as e:
        st.error(f"DB更新エラー: {e}")
        return False

# ==========================================
#   通知設定用
# ==========================================
@st.cache_data(ttl=15)
def get_choices_df(_client):
    try:
        sh = _client.open_by_key(SPREADSHEET_ID)
        try: sheet = sh.worksheet(CHOICES_SHEET_NAME)
        except: return pd.DataFrame(columns=['サイト', 'カテゴリ', 'チャンネル'])
        data = sheet.get_all_values()
        if len(data) < 2: return pd.DataFrame(columns=['サイト', 'カテゴリ', 'チャンネル'])
        
        headers = [str(h).strip() for h in data[0]]
        return pd.DataFrame(data[1:], columns=headers).astype(str)
    except: return pd.DataFrame(columns=['サイト', 'カテゴリ', 'チャンネル'])

@st.cache_data(ttl=60)
def load_data(_client):
    try:
        sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        data = sheet.get_all_values()
        final_cols = ['ユーザーID', '検索条件', 'キーワード']
        if not data: return pd.DataFrame(columns=final_cols)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        if 'サイト' in df.columns and '検索条件' not in df.columns:
            df['検索条件'] = df['サイト'] + " - " + df['カテゴリ']
        if 'ブランドキーワード' in df.columns and 'キーワード' not in df.columns:
            df['キーワード'] = df['ブランドキーワード']
        for col in final_cols:
            if col not in df.columns: df[col] = ""
        return df[final_cols]
    except: return None

def get_allowed_options(client, restriction_type):
    choices_df = get_choices_df(client)
    allowed = []
    if choices_df.empty: return []
    
    for _, row in choices_df.drop_duplicates().iterrows():
        site = str(row.get('サイト', '')).strip()
        cat = str(row.get('カテゴリ', '')).strip()
        kind = str(row.get('チャンネル', '')).replace(' ', '').replace('　', '').strip()
        
        if not site: continue
        combo_name = f"{site} - {cat}"
        
        item_type = 'other'
        if kind == 'アパレル': item_type = 'apparel'
        elif kind == 'アパレル以外': item_type = 'not_apparel'
        
        if restriction_type == 'all': allowed.append(combo_name)
        elif restriction_type == 'apparel' and item_type == 'apparel': allowed.append(combo_name)
        elif restriction_type == 'not_apparel' and item_type == 'not_apparel': allowed.append(combo_name)
            
    return sorted(list(set(allowed)))

def validate_keywords(df):
    for index, row in df.iterrows():
        kws = str(row['キーワード']).replace('、', ',').split(',')
        kws = [k for k in kws if k.strip()]
        if len(kws) > 20: return False, f"エラー: {row['検索条件']} のキーワードが多すぎます（最大20単語まで）"
    return True, ""

def save_merged_data(client, full_df, edited_display_df, user_id, restriction_type):
    try:
        is_valid, err_msg = validate_keywords(edited_display_df)
        if not is_valid:
            st.error(err_msg)
            return None
        
        allowed_opts = get_allowed_options(client, restriction_type)
        new_rows = []
        for i, row in edited_display_df.iterrows():
            combo = str(row.get('検索条件', '')).strip()
            keywords = str(row.get('キーワード', '')).strip()
            
            # 空のデータやエラープレースホルダーは保存をスキップ
            if combo in ["", "None", "nan", "NaN", "(データなし)"]: continue
            
            if combo not in allowed_opts:
                r_text = "アパレルのみ" if restriction_type == "apparel" else "アパレル以外のみ"
                if restriction_type == "all": r_text = "全て"
                st.error(f"保存失敗: 「{combo}」は現在のプラン設定（{r_text}）では選択できません。削除してください。")
                return None
            
            new_rows.append({'ユーザーID': str(user_id), '検索条件': combo, 'キーワード': keywords})
        
        save_user_df = pd.DataFrame(new_rows)
        other_users_df = full_df[full_df['ユーザーID'] != str(user_id)]
        
        cols = ['ユーザーID', '検索条件', 'キーワード']
        for c in cols:
            if c not in save_user_df.columns: save_user_df[c] = ""
            if c not in other_users_df.columns: other_users_df[c] = ""
            
        final_df = pd.concat([other_users_df, save_user_df], ignore_index=True)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        update_data = [final_df.columns.tolist()] + final_df.astype(str).values.tolist()
        sheet.clear()
        sheet.update('A1', update_data)
        load_data.clear()
        st.success(f"✅ 設定保存完了 ({len(save_user_df)}件)")
        return final_df
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return None

# ==========================================
#   メイン
# ==========================================
def main():
    client = get_gspread_client()
    if not client: return

    ensure_users_sheet(client)

    if "session_id" in st.query_params:
        session_id = st.query_params["session_id"]
        with st.spinner("お支払いを処理しています..."):
            session = get_stripe_session_details(session_id)
            if session and session.payment_status == 'paid':
                target_uid = session.metadata.get('user_id') or session.client_reference_id
                if target_uid:
                    users_df = get_users_df(client)
                    target_user = users_df[users_df['ユーザーID'] == str(target_uid)]
                    if not target_user.empty:
                        saved_restriction, saved_plan_id = get_user_temp_settings(client, target_uid)
                        update_user_stripe_data(
                            client, target_uid, stripe_id=session.customer, 
                            subscription_id=session.subscription, plan_id=saved_plan_id, 
                            restriction_type=saved_restriction, valid_until="" 
                        )
                        st.balloons()
                        st.success("🎉 お支払いが完了しました！プランが有効になりました。")
                        time.sleep(3)
                        st.query_params.clear()
                        st.session_state['logged_in_user_id'] = target_uid
                        st.session_state['logged_in_user_name'] = target_user.iloc[0]['ユーザー名']
                        st.rerun()
                    else: st.error("ユーザー情報の照合に失敗しました。")
                else: st.error("セッション情報からユーザーを特定できませんでした。")
            else:
                st.error("お支払いが完了していないか、セッションが無効です。")
                if st.button("トップへ戻る"): st.query_params.clear(); st.rerun()
        st.stop()

    if 'logged_in_user_id' not in st.session_state:
        st.session_state['logged_in_user_id'] = None
        st.session_state['logged_in_user_name'] = None
    
    if 'temp_login_user_id' not in st.session_state:
        st.session_state['temp_login_user_id'] = None
        st.session_state['temp_login_user_name'] = None
        st.session_state['temp_login_secret'] = None

    if st.session_state['logged_in_user_id'] is None:
        if st.session_state['temp_login_user_id'] is not None:
            st.subheader("🔐 2段階認証")
            st.info("認証アプリに表示されている6桁のコードを入力してください。")
            otp_code = st.text_input("認証コード", max_chars=6, key="otp_login")
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("認証する", type="primary"):
                    totp = pyotp.TOTP(st.session_state['temp_login_secret'])
                    if totp.verify(otp_code):
                        st.session_state['logged_in_user_id'] = st.session_state['temp_login_user_id']
                        st.session_state['logged_in_user_name'] = st.session_state['temp_login_user_name']
                        st.session_state['temp_login_user_id'] = None
                        st.session_state['temp_login_secret'] = None
                        st.rerun()
                    else: st.error("コードが正しくありません")
            with col2:
                if st.button("キャンセル"): st.session_state['temp_login_user_id'] = None; st.rerun()
            st.stop()

        st.markdown("## 📊 ツウチマネージャー (市場リサーチツール)")
        st.markdown("""
        **【サービス概要】**
        リユース市場における商品価格や在庫状況を横断的に分析・可視化するSaaS型リサーチツールです。
        Web上の公開情報をシステムが整理して提供することで、市場調査や適正価格の把握にかかる時間を短縮し、業務効率化を支援します。
        
        **【料金プラン】**
        * **ライトプラン (月額 5,000円)** : アパレルまたはそれ以外の片方カテゴリのみ
        * **フルプラン (月額 9,000円)** : 全てのカテゴリ
        * **キーワード通知オプション (+月額 2,000円)** : キーワード絞り込み機能
        """)
        st.markdown("---")
        st.info("👇 既存ユーザーはログイン、新規の方はご登録をお願いいたします。")

        tab1, tab2 = st.tabs(["🔑 ログイン", "✨ 新規登録"])
        with tab1:
            l_input = st.text_input("ID / 名前", key="li", max_chars=50)
            l_pass = st.text_input("パスワード", type="password", key="lp", max_chars=50)
            if st.button("ログイン", type="primary"):
                suc, msg, uid, uname, secret = login_user(client, l_input, l_pass)
                if suc:
                    if secret and len(secret) > 0:
                        st.session_state['temp_login_user_id'] = uid
                        st.session_state['temp_login_user_name'] = uname
                        st.session_state['temp_login_secret'] = secret
                        st.rerun()
                    else:
                        st.session_state['logged_in_user_id'] = uid
                        st.session_state['logged_in_user_name'] = uname
                        st.rerun()
                else: st.error(msg)
        with tab2:
            r_id = st.text_input("Discord ID", key="ri", max_chars=50)
            r_name = st.text_input("表示名", key="rn", max_chars=50)
            r_pass = st.text_input("パスワード", type="password", key="rp", max_chars=50)
            if st.button("登録"):
                if not r_id or not r_name or not r_pass: st.error("入力不足")
                else:
                    suc, msg = register_user(client, r_id, r_name, r_pass)
                    if suc: st.success(msg); st.balloons()
                    else: st.error(msg)
        
        show_tokushoho()
        st.stop()

    uid = st.session_state['logged_in_user_id']
    uname = st.session_state['logged_in_user_name']
    
    users_df = get_users_df(client)
    if users_df[users_df['ユーザーID'] == str(uid)].empty:
        st.error("ユーザー情報が見つかりません")
        st.session_state['logged_in_user_id'] = None
        st.stop()
        
    user_row = users_df[users_df['ユーザーID'] == str(uid)].iloc[0]
    sub_id = str(user_row.get('subscription_id', ''))
    current_plan_id = str(user_row.get('plan_id', ''))
    channel_url = str(user_row.get('チャンネルURL', ''))
    restriction_type = str(user_row.get('plan', 'all'))
    if not restriction_type: restriction_type = 'all'
    user_secret_key = str(user_row.get('secret_key', '')).strip()
    
    valid_until_str = str(user_row.get('valid_until', '')).strip()
    is_period_active = False
    if valid_until_str:
        try:
            v_date_str = valid_until_str.split(' ')[0] 
            if datetime.now(timezone(timedelta(hours=9))).date() <= datetime.strptime(v_date_str, '%Y/%m/%d').date():
                is_period_active = True
        except: pass

    has_active_subscription = (sub_id != "" and sub_id.lower() not in ["nan", "none"])
    is_access_allowed = has_active_subscription or is_period_active
    has_option = (current_plan_id in [PLANS["full"]["opt_id"], PLANS["light"]["opt_id"]])

    with st.sidebar:
        st.write(f"User: **{uname}**")
        menu = st.radio("メニュー", ["通知設定", "プラン契約・解約", "アカウント設定"])
        if st.button("ログアウト"): st.session_state['logged_in_user_id'] = None; st.rerun()

    full_df = load_data(client)

    if menu == "通知設定":
        st.subheader("📢 通知条件の設定")

        if not is_access_allowed:
            st.error("⚠️ この機能を利用するにはプラン契約が必要です")
            st.info("左側のメニュー「プラン契約・解約」から、プランへの加入手続きを行ってください。")
            st.stop()
        
        if not has_active_subscription and is_period_active:
            st.warning(f"⚠️ 解約済みですが、有効期限 ({valid_until_str}) までは機能をご利用いただけます。")

        allowed_opts = get_allowed_options(client, restriction_type)
        if not allowed_opts:
            st.error("⚠️ スプレッドシートの「管理」シートから、現在のプランで選択できるカテゴリが見つかりませんでした。")
            with st.expander("🔍 原因を調べる（クリックして展開）"):
                debug_df = get_choices_df(client)
                st.write(f"・「管理」シートから取得できたデータ数: **{len(debug_df)}件**")
                st.write(f"・あなたの現在のプラン設定: **{restriction_type}**")
                st.write("【よくある原因】")
                st.write("1. 「管理」シートの1行目の列名が「サイト」「カテゴリ」「チャンネル」に完全一致していない。")
                st.write("2. 「チャンネル」列に「アパレル」または「アパレル以外」という文字が入っていない（空白や別の言葉になっている）。")
                st.write("👇 現在プログラム側が読み取っている「管理」シートの中身は以下の通りです。")
                st.dataframe(debug_df)
            allowed_opts = ["(データなし)"]

        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        
        if not user_df.empty and '検索条件' in user_df.columns:
            display_df = user_df[['検索条件', 'キーワード']].copy()
            invalid_vals = ['None', 'none', 'nan', 'NaN', '', '(設定エラー)', '(データなし)']
            display_df = display_df[~display_df['検索条件'].astype(str).str.strip().isin(invalid_vals)]
        else:
            display_df = pd.DataFrame(columns=['検索条件', 'キーワード'])

        display_df = display_df.reset_index(drop=True)
        display_df['検索条件'] = display_df['検索条件'].astype(str)
        display_df['キーワード'] = display_df['キーワード'].astype(str)

        if current_plan_id.startswith(PLANS["full"]["base_id"]) or current_plan_id == PLANS["full"]["opt_id"]:
             st.info("💎 **フルプラン契約中**")
        elif current_plan_id.startswith(PLANS["light"]["base_id"]) or current_plan_id == PLANS["light"]["opt_id"]:
             st.info("💡 **ライトプラン契約中**")
             r_text = "👜 アパレルのみ" if restriction_type == "apparel" else "📷 アパレル以外のみ"
             st.caption(f"選択可能カテゴリ: {r_text}")

        if has_option:
            st.success("✅ **キーワード通知オプション: 有効**")
            st.caption("商品名、ブランド、型番のいずれかに設定したキーワード（最大20単語）が含まれる商品のみを通知します。")
        else:
            st.warning("🔒 **キーワード通知オプション: 無効**")
            st.caption("現在、キーワードによる絞り込み機能は利用できません。ご希望の場合はプラン契約画面からオプションを追加してください。")

        with st.expander("📡 あなたの通知チャンネル"):
            if channel_url:
                st.success("✅ Discord連携済み")
                st.code(channel_url)
            else:
                st.warning("⚠️ チャンネル情報が登録されていません。")

        edited = st.data_editor(
            display_df, 
            num_rows="dynamic", 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "検索条件": st.column_config.SelectboxColumn(
                    "検索条件",
                    options=allowed_opts
                ),
                "キーワード": st.column_config.TextColumn(
                    "キーワード (最大20個)",
                    disabled=(not has_option),
                    help="カンマ(,)区切りで入力。商品名・ブランド・型番のいずれかに一致したら通知。"
                )
            }
        )
        
        if st.button("設定を保存", type="primary"):
            save_merged_data(client, full_df, edited, uid, restriction_type)

    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        
        if has_active_subscription:
            st.success("✅ **現在プラン契約中です** (次回更新あり)")
            
            current_plan_name = "不明"
            is_full = False; is_light = False
            
            if current_plan_id in [PLANS["full"]["base_id"], PLANS["full"]["opt_id"]]:
                is_full = True; current_plan_name = PLANS["full"]["name"]
            elif current_plan_id in [PLANS["light"]["base_id"], PLANS["light"]["opt_id"]]:
                is_light = True; current_plan_name = PLANS["light"]["name"]
                
            if has_option: current_plan_name += " + オプション"
            
            col1, col2 = st.columns(2)
            col1.write(f"**契約プラン**: {current_plan_name}")
            if is_light:
                r_text = "👜 アパレルのみ" if restriction_type == "apparel" else "📷 アパレル以外のみ"
                col1.write(f"**選択カテゴリ**: {r_text}")
            
            with st.expander("🔄 プラン内容を変更する"):
                st.info("プラン変更やオプションの追加・解除を行います。")
                new_plan_key = st.radio("プラン選択", ["full", "light"], index=0 if is_full else 1, format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
                new_restriction = "all"
                if new_plan_key == "light":
                    sub_choice = st.radio("カテゴリ選択", ["apparel", "not_apparel"], index=1 if restriction_type == "not_apparel" else 0, format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外")
                    new_restriction = sub_choice
                
                new_option = st.checkbox(f"✨ **キーワード通知オプション (+¥{OPTION_PRICE:,})**", value=has_option)
                new_total_price = PLANS[new_plan_key]['base_price'] + (OPTION_PRICE if new_option else 0)
                new_target_id = PLANS[new_plan_key]['opt_id'] if new_option else PLANS[new_plan_key]['base_id']
                
                st.write(f"**変更後の料金**: ¥{new_total_price:,} / 月")
                if st.button("プランを変更する"):
                    if new_target_id == current_plan_id and new_restriction == restriction_type: st.warning("変更内容がありません。")
                    else:
                        with st.spinner("変更処理中..."):
                            success_update = True
                            if new_target_id != current_plan_id:
                                suc, msg = change_stripe_subscription_plan(sub_id, new_target_id)
                                if not suc: st.error(f"Stripe更新エラー: {msg}"); success_update = False
                            if success_update:
                                update_user_stripe_data(client, uid, plan_id=new_target_id, restriction_type=new_restriction)
                                st.success("プラン変更が完了しました！"); time.sleep(2); st.rerun()

            st.markdown("---")
            if st.button("プランを解約する"):
                with st.spinner("解約処理中..."):
                    suc, msg = cancel_stripe_subscription_at_period_end(sub_id)
                    
                    if suc:
                        # ▼修正: Stripe上に存在しなかった場合は即時解約扱いにしてシステムをリセット
                        if msg == "ALREADY_CANCELED":
                            now_str = datetime.now(timezone(timedelta(hours=9))).strftime('%Y/%m/%d')
                            update_user_stripe_data(client, uid, subscription_id="", valid_until=now_str)
                            st.success("Stripe上に契約が存在しなかったため、システムの契約情報をリセットしました。"); time.sleep(3); st.rerun()
                        else:
                            update_user_stripe_data(client, uid, subscription_id="", valid_until=msg)
                            st.success(f"解約予約を受け付けました。{msg} までは引き続きご利用いただけます。"); time.sleep(3); st.rerun()
                    else:
                        st.error(f"解約エラー: {msg}")

        elif not has_active_subscription and is_period_active:
            st.warning(f"⚠️ 解約済みですが、有効期限 ({valid_until_str}) までは現在のプランをご利用いただけます。")
            st.info("再度契約を再開したい場合は、以下からプランを選択してください。")
            plan_key = st.radio("プラン選択", ["full", "light"], format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
            selected_restriction = "all"
            if plan_key == "light": selected_restriction = st.radio("カテゴリ選択", ["apparel", "not_apparel"], format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外")
            st.markdown("---")
            use_option = st.checkbox(f"✨ **キーワード通知オプションを追加する (+¥{OPTION_PRICE:,})**")
            final_price = PLANS[plan_key]['base_price'] + (OPTION_PRICE if use_option else 0)
            target_plan_id = PLANS[plan_key]['opt_id'] if use_option else PLANS[plan_key]['base_id']

            st.write(f"**選択中: {PLANS[plan_key]['name']}**")
            st.subheader(f"ご請求額: ¥{final_price:,} / 月")
            if st.button("定期購読を再開する (Stripeへ移動)"):
                if not stripe.api_key: st.error("API設定エラー"); st.stop()
                with st.spinner("決済ページを準備中..."):
                    update_user_temp_settings(client, uid, selected_restriction, target_plan_id)
                    suc, url_or_msg = create_stripe_checkout_session(uid, target_plan_id)
                    if suc: st.link_button("👉 ここをクリックして支払いを完了させる", url_or_msg, type="primary")
                    else: st.error(f"エラー: {url_or_msg}")
        else:
            st.info("利用を開始するには、以下のプランから選択してください。")
            plan_key = st.radio("プラン選択", ["full", "light"], format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
            selected_restriction = "all"
            if plan_key == "light": selected_restriction = st.radio("カテゴリ選択", ["apparel", "not_apparel"], format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外")
            st.markdown("---")
            use_option = st.checkbox(f"✨ **キーワード通知オプションを追加する (+¥{OPTION_PRICE:,})**")
            final_price = PLANS[plan_key]['base_price'] + (OPTION_PRICE if use_option else 0)
            target_plan_id = PLANS[plan_key]['opt_id'] if use_option else PLANS[plan_key]['base_id']

            st.write(f"**選択中: {PLANS[plan_key]['name']}**")
            if plan_key == "light": st.info(f"選択カテゴリ: {'👜 アパレル' if selected_restriction == 'apparel' else '📷 アパレル以外'}")
            if use_option: st.success(f"オプション適用: あり (+¥{OPTION_PRICE:,})")
            st.subheader(f"ご請求額: ¥{final_price:,} / 月")
            if st.button("お支払い画面へ進む (Stripeへ移動)"):
                if not stripe.api_key: st.error("API設定エラー"); st.stop()
                with st.spinner("決済ページを準備中..."):
                    update_user_temp_settings(client, uid, selected_restriction, target_plan_id)
                    suc, url_or_msg = create_stripe_checkout_session(uid, target_plan_id)
                    if suc: st.link_button("👉 ここをクリックして支払いを完了させる", url_or_msg, type="primary")
                    else: st.error(f"エラー: {url_or_msg}")

    elif menu == "アカウント設定":
        st.subheader("⚙️ アカウント設定")
        with st.expander("🔑 パスワードの変更", expanded=False):
            with st.form("password_reset_form"):
                current_pw = st.text_input("現在のパスワード", type="password")
                new_pw = st.text_input("新しいパスワード", type="password")
                new_pw_confirm = st.text_input("新しいパスワード（確認）", type="password")
                if st.form_submit_button("パスワードを変更する"):
                    if not current_pw or not new_pw or not new_pw_confirm: st.error("全ての項目を入力してください")
                    elif new_pw != new_pw_confirm: st.error("新しいパスワードが一致しません")
                    elif hash_password(current_pw) != user_row.get('パスワードハッシュ', ''): st.error("現在のパスワードが間違っています")
                    else:
                        with st.spinner("更新中..."):
                            suc, msg = update_user_password(client, uid, new_pw)
                            if suc: st.success(msg)
                            else: st.error(msg)
        st.markdown("---")
        st.subheader("🛡️ 2段階認証 (2FA)")
        if user_secret_key:
            st.success("✅ **2段階認証は現在「有効」です**")
            if st.button("2段階認証を解除する", type="primary"):
                if update_user_secret(client, uid, ""): st.warning("2段階認証を解除しました。"); time.sleep(1); st.rerun()
        else:
            st.warning("⚠️ **2段階認証は設定されていません**")
            if '2fa_setup_secret' not in st.session_state: st.session_state['2fa_setup_secret'] = pyotp.random_base32()
            secret = st.session_state['2fa_setup_secret']
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=uname, issuer_name="MyApp")
            qr_img = qrcode.make(uri)
            img_byte_arr = io.BytesIO()
            qr_img.save(img_byte_arr, format='PNG')
            col1, col2 = st.columns([1, 2])
            with col1: st.image(img_byte_arr.getvalue(), caption="認証アプリでスキャン", width=200)
            with col2:
                st.markdown(f"1. アプリでスキャン\n2. 6桁のコードを入力\n\n**シークレットキー:** `{secret}`")
                verify_code = st.text_input("6桁のコード", max_chars=6, key="otp_setup")
                if st.button("有効にする"):
                    if pyotp.TOTP(secret).verify(verify_code):
                        if update_user_secret(client, uid, secret):
                            st.success("🎉 有効になりました！"); del st.session_state['2fa_setup_secret']; time.sleep(2); st.rerun()
                        else: st.error("保存失敗")
                    else: st.error("コード間違い")

if __name__ == "__main__":
    main()
