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
from PIL import Image
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError

# ==========================================
#   設定・定数
# ==========================================
# ★ アプリのURL (決済完了後に戻ってくる場所)
APP_BASE_URL = "https://discord-notify-tool.streamlit.app/"

CREDENTIALS_PATH = 'google_credentials.json'
TOKEN_PATH = 'gspread_token.json'

SPREADSHEET_ID = "1Y8VEVn95FOp5ELLtBiuUrB9m4S3qDSiX50G6aB88vnk"
TARGET_SHEET_NAME = "ユーザー設定"
USERS_SHEET_NAME = "ユーザー管理"
CHOICES_SHEET_NAME = "管理"

# ★ マシン設定
MACHINES = ["machine_1", "machine_2"]

# Secrets読み込み
try:
    DISCORD_BOT_TOKEN = st.secrets["discord"]["bot_token"]
    DISCORD_GUILD_ID = st.secrets["discord"]["guild_id"]
except Exception:
    DISCORD_BOT_TOKEN = ""
    DISCORD_GUILD_ID = ""

# ★ プラン設定
OPTION_PRICE = 2000
PLANS = {
    "full": {
        "name": "フルプラン (全て)",
        "desc": "アパレル・その他の全てのカテゴリを選択可能",
        "type": "all",
        "base_price": 9000,
        "base_id": "plan_9000",
        "opt_id": "plan_11000"
    },
    "light": {
        "name": "ライトプラン (片方のみ)",
        "desc": "「アパレル」または「それ以外」のどちらか一方のみ選択可能",
        "type": "select",
        "base_price": 5000,
        "base_id": "plan_5000",
        "opt_id": "plan_7000"
    }
}

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

st.set_page_config(page_title="通知設定マネージャー", layout="wide")

# ==========================================
#   Secrets & 認証処理
# ==========================================
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
        st.error(f"Secrets読み込みエラー: {e}")

create_json_from_secrets()

# Fincode設定読み込み
try:
    FINCODE_API_KEY = st.secrets["fincode"]["api_key"]
    FINCODE_BASE_URL = st.secrets["fincode"]["base_url"]
except Exception:
    FINCODE_API_KEY = ""
    FINCODE_BASE_URL = ""

HEADERS = {
    "Authorization": f"Bearer {FINCODE_API_KEY}",
    "Content-Type": "application/json"
}

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
    with st.expander("⚖️ 特定商取引法に基づく表記"):
        st.markdown("""
        | 項目 | 内容 |
        | :--- | :--- |
        | **販売業者** | 齋藤 航太 |
        | **代表責任者** | 齋藤 航太 |
        | **所在地** | 〒156-0055 東京都世田谷区船橋2-8-1 |
        | **電話番号** | 080-3423-1798 |
        | **メールアドレス** | koutaiwi@gmail.com |
        | **販売価格** | プラン契約画面に記載 |
        | **支払方法** | クレジットカード決済 |
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
            {
                "id": DISCORD_GUILD_ID,
                "type": 0,
                "deny": "1024"
            },
            {
                "id": user_discord_id,
                "type": 1,
                "allow": "1024"
            }
        ]
    }
    
    res = requests.post(url_create, json=payload, headers=headers)
    if res.status_code not in [200, 201]:
        return False, f"チャンネル作成失敗: {res.text}"
    
    channel_data = res.json()
    channel_id = channel_data["id"]

    url_webhook = f"https://discord.com/api/v10/channels/{channel_id}/webhooks"
    webhook_payload = {"name": "新着通知Bot"}
    res_wh = requests.post(url_webhook, json=webhook_payload, headers=headers)
    if res_wh.status_code not in [200, 201]:
        return False, f"Webhook作成失敗: {res_wh.text}"
        
    webhook_data = res_wh.json()
    return True, webhook_data["url"]

# ==========================================
#   Fincode API (3Dセキュア対応版)
# ==========================================
def fincode_register_customer(user_id):
    url = f"{FINCODE_BASE_URL}/customers"
    data = {"id": str(user_id), "description": f"User: {user_id}"}
    response = requests.post(url, json=data, headers=HEADERS)
    return response.json()

# ★ 修正: key名を order_id -> id に変更
def fincode_create_subscription_session_debug(customer_id, plan_id, return_url):
    url = f"{FINCODE_BASE_URL}/sessions"
    
    current_ts = int(time.time())
    order_id = f"sub_{customer_id}_{current_ts}"

    success_url = return_url
    cancel_url = return_url 
    
    data = {
        "id": order_id, # ★ここを修正しました (order_id -> id)
        "pay_type": "Card", 
        "transaction_type": "Subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "return_url": return_url,
        "customer_id": customer_id,
        "plan_id": plan_id,
        "guide_mail_send_flag": "1",
        "shop_service_name": "NotificationTool",
        
        # 3Dセキュア項目
        "tds_type": "2",
        "tds2_type": "3",
        "merchant_name": "NotificationTool"
    }
    
    # デバッグ表示（確認用）
    # st.markdown("### 🛠 デバッグ情報: 送信データ")
    # st.json(data)
    
    res = requests.post(url, json=data, headers=HEADERS)
    
    if res.status_code != 200:
        st.markdown(f"### ⚠️ エラー受信 (Status: {res.status_code})")
        try:
            st.json(res.json())
        except:
            st.write(res.text)
            
    return res.json()

def fincode_retrieve_session(session_id):
    url = f"{FINCODE_BASE_URL}/sessions/{session_id}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    return None

def fincode_update_subscription(subscription_id, plan_id):
    url = f"{FINCODE_BASE_URL}/subscriptions/{subscription_id}"
    data = {
        "pay_type": "Card",
        "plan_id": plan_id
    }
    res = requests.put(url, json=data, headers=HEADERS).json()
    if "errors" in res:
        return False, res["errors"][0]["error_message"]
    return True, "変更完了"

def fincode_get_subscription(subscription_id):
    url = f"{FINCODE_BASE_URL}/subscriptions/{subscription_id}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    return None

def fincode_cancel_subscription(subscription_id):
    url = f"{FINCODE_BASE_URL}/subscriptions/{subscription_id}"
    params = {"pay_type": "Card"}
    res = requests.delete(url, headers=HEADERS, params=params).json()
    if "errors" in res:
        return False, res["errors"][0]["error_message"]
    return True, "解約しました"

# ==========================================
#   ユーザー管理・DB操作
# ==========================================
def hash_password(password):
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def ensure_users_sheet(client):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        
        expected_headers = [
            'ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 
            'subscription_id', 'plan_id', 'チャンネルURL', 'plan', 'valid_until', 
            'assigned_machine', 'secret_key', 'failed_count', 'locked_until', 'temp_plan_settings'
        ]

        try:
            ws = sh.worksheet(USERS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=14)
            ws.append_row(expected_headers)
            return

        if ws.col_count < 14:
            ws.resize(cols=14)
            print("列数を拡張しました")

        headers = ws.row_values(1)
        needs_update = False
        if len(headers) < 14:
            headers += [""] * (14 - len(headers))
            needs_update = True
        
        for i, h in enumerate(expected_headers):
            if i < len(headers) and headers[i] == "":
                headers[i] = h
                needs_update = True
        
        if needs_update:
            ws.update('A1:N1', [headers])
            print("ヘッダーを修復しました")

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
                'ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 
                'subscription_id', 'plan_id', 'チャンネルURL', 'plan', 'valid_until', 
                'assigned_machine', 'secret_key', 'failed_count', 'locked_until', 'temp_plan_settings'
            ]
            
            if len(data) < 2:
                return pd.DataFrame(columns=cols)
            
            current_cols = data[0]
            df = pd.DataFrame(data[1:], columns=current_cols).astype(str)
            
            for c in cols:
                if c not in df.columns: df[c] = ""
            return df
        except APIError as e:
            if "429" in str(e) and i < max_retries - 1:
                time.sleep(2 ** i)
                continue
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

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
        if not cell:
            return False, "ユーザーIDまたはパスワードが間違っています", "", "", ""
        
        row_values = ws.row_values(cell.row)
        if len(row_values) < 14:
            row_values += [""] * (14 - len(row_values))
            
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
                    return False, f"アカウントはロックされています。あと約{remain}分後に再度お試しください。", "", "", ""
            except:
                pass
        
        if stored_hash == hash_password(password):
            if failed_count_str != "0" or locked_until_str != "":
                ws.update_cell(cell.row, 12, "0")
                ws.update_cell(cell.row, 13, "")
            return True, "成功", user_id, user_name, secret_key
        else:
            try:
                current_fail = int(failed_count_str) if failed_count_str.isdigit() else 0
            except:
                current_fail = 0
                
            new_fail = current_fail + 1
            ws.update_cell(cell.row, 12, str(new_fail))
            
            if new_fail >= 10:
                lock_until = now + timedelta(minutes=30)
                lock_str = lock_until.strftime('%Y-%m-%d %H:%M:%S')
                ws.update_cell(cell.row, 13, lock_str)
                return False, "ログインに連続して失敗したため、アカウントを一時的にロックしました（30分間）。", "", "", ""
            
            return False, "ユーザーIDまたはパスワードが間違っています", "", "", ""

    except Exception as e:
        return False, f"ログイン処理エラー: {e}", "", "", ""

def update_user_password(client, user_id, new_password):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            new_hash = hash_password(new_password)
            ws.update_cell(cell.row, 3, new_hash)
            get_users_df.clear()
            return True, "パスワードを変更しました"
        return False, "ユーザーが見つかりません"
    except Exception as e:
        return False, f"更新エラー: {e}"

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
    except Exception as e:
        st.error(f"Secret保存エラー: {e}")
        return False

def update_user_temp_settings(client, user_id, restriction_type):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            ws.update_cell(cell.row, 14, restriction_type)
            return True
        return False
    except: return False

def get_user_temp_settings(client, user_id):
    try:
        users_df = get_users_df(client)
        row = users_df[users_df['ユーザーID'] == str(user_id)]
        if not row.empty:
            return str(row.iloc[0].get('temp_plan_settings', 'all'))
        return 'all'
    except: return 'all'

def update_user_fincode_data(client, user_id, fincode_id=None, subscription_id=None, plan_id=None, restriction_type=None, valid_until=None):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            if fincode_id is not None: ws.update_cell(cell.row, 4, fincode_id)
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
@st.cache_data(ttl=60)
def get_choices_df(_client):
    try:
        sh = _client.open_by_key(SPREADSHEET_ID)
        try: sheet = sh.worksheet(CHOICES_SHEET_NAME)
        except: return pd.DataFrame(columns=['サイト', 'カテゴリ', '種類'])
        data = sheet.get_all_values()
        if len(data) < 2: return pd.DataFrame(columns=['サイト', 'カテゴリ', '種類'])
        return pd.DataFrame(data[1:], columns=data[0]).astype(str)
    except: return pd.DataFrame(columns=['サイト', 'カテゴリ', '種類'])

@st.cache_data(ttl=60)
def load_data(_client):
    try:
        sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        data = sheet.get_all_values()
        final_cols = ['ユーザーID', '検索条件', 'キーワード']
        if not data: return pd.DataFrame(columns=final_cols)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        if 'サイト' in df.columns:
            if '検索条件' not in df.columns: df['検索条件'] = df['サイト'] + " - " + df['カテゴリ']
        
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
        kind = str(row.get('種類', '')).strip()
        
        if not site: continue
        combo_name = f"{site} - {cat}"
        
        item_type = 'other'
        if kind == 'アパレル': item_type = 'apparel'
        elif kind == 'アパレル以外': item_type = 'not_apparel'
        
        if restriction_type == 'all':
            allowed.append(combo_name)
        elif restriction_type == 'apparel' and item_type == 'apparel':
            allowed.append(combo_name)
        elif restriction_type == 'not_apparel' and item_type == 'not_apparel':
            allowed.append(combo_name)
            
    return sorted(list(set(allowed)))

def validate_keywords(df):
    for index, row in df.iterrows():
        kws = str(row['キーワード']).replace('、', ',').split(',')
        kws = [k for k in kws if k.strip()]
        if len(kws) > 20:
            return False, f"エラー: {row['検索条件']} のキーワードが多すぎます（最大20単語まで）"
    return True, ""

def save_merged_data(client, full_df, edited_display_df, user_id, restriction_type):
    try:
        is_valid, err_msg = validate_keywords(edited_display_df)
        if not is_valid:
            st.error(err_msg)
            return None
        
        allowed_opts = get_allowed_options(client, restriction_type)
        for i, row in edited_display_df.iterrows():
            combo = row['検索条件']
            if combo and combo not in allowed_opts:
                r_text = "アパレルのみ" if restriction_type == "apparel" else "アパレル以外のみ"
                if restriction_type == "all": r_text = "全て"
                
                st.error(f"保存失敗: 「{combo}」は現在のプラン設定（{r_text}）では選択できません。削除してください。")
                return None

        new_rows = []
        for i, row in edited_display_df.iterrows():
            combo = row['検索条件']
            keywords = row['キーワード']
            if not combo or not isinstance(combo, str): continue
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
    st.title("🔔 通知設定＆サブスク管理")
    client = get_gspread_client()
    if not client: return

    ensure_users_sheet(client)

    # ----------------------------------------
    # ★ 決済完了後のコールバック処理
    # ----------------------------------------
    if "session_id" in st.query_params:
        session_id = st.query_params["session_id"]
        
        with st.spinner("決済情報を確認中..."):
            session_data = fincode_retrieve_session(session_id)
            
            if session_data and session_data.get("status") == "COMPLETED":
                f_cust_id = session_data.get("customer_id")
                plan_id = session_data.get("plan_id")
                
                users_df = get_users_df(client)
                target_user = users_df[users_df['fincode_customer_id'] == f_cust_id]
                
                if not target_user.empty:
                    uid = target_user.iloc[0]['ユーザーID']
                    saved_restriction = target_user.iloc[0].get('temp_plan_settings', 'all')
                    
                    sub_list_res = requests.get(f"{FINCODE_BASE_URL}/subscriptions", params={"customer_id": f_cust_id}, headers=HEADERS)
                    new_sub_id = ""
                    if sub_list_res.status_code == 200:
                        s_list = sub_list_res.json().get("list", [])
                        if s_list:
                            new_sub_id = s_list[0]["id"]

                    update_user_fincode_data(client, uid, subscription_id=new_sub_id, plan_id=plan_id, restriction_type=saved_restriction, valid_until="")
                    
                    st.balloons()
                    st.success("🎉 お支払いが完了しました！プランが有効になりました。")
                    time.sleep(3)
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.error("ユーザー情報の照合に失敗しました。管理者にお問い合わせください。")
            else:
                st.error("決済が完了していません。もう一度お試しください。")
                if st.button("トップへ戻る"):
                    st.query_params.clear()
                    st.rerun()
        st.stop()

    # ----------------------------------------
    # 以下、通常のアプリフロー
    # ----------------------------------------

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
                    secret = st.session_state['temp_login_secret']
                    totp = pyotp.TOTP(secret)
                    if totp.verify(otp_code):
                        st.session_state['logged_in_user_id'] = st.session_state['temp_login_user_id']
                        st.session_state['logged_in_user_name'] = st.session_state['temp_login_user_name']
                        st.session_state['temp_login_user_id'] = None
                        st.session_state['temp_login_user_name'] = None
                        st.session_state['temp_login_secret'] = None
                        st.rerun()
                    else:
                        st.error("コードが正しくありません")
            with col2:
                if st.button("キャンセル"):
                    st.session_state['temp_login_user_id'] = None
                    st.rerun()
            st.stop()

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
                else:
                    st.error(msg)
        with tab2:
            st.info("DiscordユーザーIDを入力してください")
            r_id = st.text_input("Discord ID", key="ri", max_chars=50)
            r_name = st.text_input("表示名", key="rn", max_chars=50)
            r_pass = st.text_input("パスワード", type="password", key="rp", max_chars=50)
            if st.button("登録"):
                if not r_id or not r_name or not r_pass: st.error("入力不足")
                else:
                    suc, msg = register_user(client, r_id, r_name, r_pass)
                    if suc: 
                        st.success(msg)
                        st.balloons()
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
            v_date = datetime.strptime(v_date_str, '%Y/%m/%d')
            now_jst = datetime.now(timezone(timedelta(hours=9)))
            if now_jst.date() <= v_date.date():
                is_period_active = True
        except:
            pass

    has_active_subscription = (sub_id != "" and sub_id.lower() != "nan" and sub_id.lower() != "none")
    is_access_allowed = has_active_subscription or is_period_active

    opt_ids = [PLANS["full"]["opt_id"], PLANS["light"]["opt_id"]]
    has_option = (current_plan_id in opt_ids)

    with st.sidebar:
        st.write(f"User: **{uname}**")
        menu = st.radio("メニュー", ["通知設定", "プラン契約・解約", "アカウント設定"])
        if st.button("ログアウト"):
            st.session_state['logged_in_user_id'] = None
            st.rerun()

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
        
        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        display_df = user_df[['検索条件', 'キーワード']] if '検索条件' in user_df.columns else pd.DataFrame(columns=['検索条件', 'キーワード'])
        
        if not display_df.empty:
            display_df = display_df.reset_index(drop=True)

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
                "_index": None,
                "検索条件": st.column_config.SelectboxColumn(
                    options=allowed_opts, 
                    required=True
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
            is_full = False
            is_light = False
            
            if current_plan_id in [PLANS["full"]["base_id"], PLANS["full"]["opt_id"]]:
                is_full = True
                current_plan_name = PLANS["full"]["name"]
            elif current_plan_id in [PLANS["light"]["base_id"], PLANS["light"]["opt_id"]]:
                is_light = True
                current_plan_name = PLANS["light"]["name"]
                
            if has_option: current_plan_name += " + オプション"
            
            col1, col2 = st.columns(2)
            col1.write(f"**契約プラン**: {current_plan_name}")
            if is_light:
                r_text = "👜 アパレルのみ" if restriction_type == "apparel" else "📷 アパレル以外のみ"
                col1.write(f"**選択カテゴリ**: {r_text}")
            
            with st.expander("🔄 プラン内容を変更する"):
                st.info("プランのアップグレード・ダウングレードや、オプションの追加・解除ができます。")
                
                new_plan_key = st.radio("プラン選択", ["full", "light"], 
                                        index=0 if is_full else 1,
                                        format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
                
                new_restriction = "all"
                if new_plan_key == "light":
                    default_idx = 0
                    if restriction_type == "not_apparel": default_idx = 1
                    
                    sub_choice = st.radio(
                        "カテゴリ選択", 
                        ["apparel", "not_apparel"],
                        index=default_idx,
                        format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外"
                    )
                    new_restriction = sub_choice
                
                new_option = st.checkbox(f"✨ **キーワード通知オプション (+¥{OPTION_PRICE:,})**", value=has_option)
                
                new_base_price = PLANS[new_plan_key]['base_price']
                new_total_price = new_base_price + (OPTION_PRICE if new_option else 0)
                new_target_id = PLANS[new_plan_key]['opt_id'] if new_option else PLANS[new_plan_key]['base_id']
                
                st.write(f"**変更後の料金**: ¥{new_total_price:,} / 月")
                
                if st.button("プランを変更する"):
                    is_plan_changed = (new_target_id != current_plan_id)
                    is_res_changed = (new_restriction != restriction_type)
                    
                    if not is_plan_changed and not is_res_changed:
                        st.warning("変更内容がありません。")
                    else:
                        with st.spinner("変更処理中..."):
                            success_update = True
                            if is_plan_changed:
                                suc, msg = fincode_update_subscription(sub_id, new_target_id)
                                if not suc:
                                    st.error(f"Fincode更新エラー: {msg}")
                                    success_update = False
                            
                            if success_update:
                                update_user_fincode_data(client, uid, plan_id=new_target_id, restriction_type=new_restriction)
                                st.success("プラン変更が完了しました！")
                                time.sleep(2)
                                st.rerun()

            st.markdown("---")
            if st.button("プランを解約する"):
                with st.spinner("解約処理中..."):
                    sub_detail = fincode_get_subscription(sub_id)
                    next_charge = ""
                    if sub_detail and "next_charge_date" in sub_detail:
                        next_charge = sub_detail["next_charge_date"]
                    
                    suc, msg = fincode_cancel_subscription(sub_id)
                    
                    if suc:
                        update_user_fincode_data(client, uid, subscription_id="", valid_until=next_charge)
                        st.success(f"解約予約を受け付けました。{next_charge} までは引き続きご利用いただけます。")
                        time.sleep(3)
                        st.rerun()
                    else:
                        st.error(f"解約エラー: {msg}")

        elif not has_active_subscription and is_period_active:
            st.warning(f"⚠️ 解約済みですが、有効期限 ({valid_until_str}) までは現在のプランをご利用いただけます。")
            st.info("再度契約を再開したい場合は、以下からプランを選択してください。")
            
            plan_key = st.radio("プラン選択", ["full", "light"], format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
            selected_plan = PLANS[plan_key]
            
            selected_restriction = "all"
            if plan_key == "light":
                st.markdown("👇 **通知を受け取るカテゴリを選択してください**")
                sub_choice = st.radio(
                    "カテゴリ選択", 
                    ["apparel", "not_apparel"], 
                    format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外"
                )
                selected_restriction = sub_choice
            
            st.markdown("---")
            use_option = st.checkbox(f"✨ **キーワード通知オプションを追加する (+¥{OPTION_PRICE:,})**")
            
            final_price = selected_plan['base_price'] + (OPTION_PRICE if use_option else 0)
            target_plan_id = selected_plan['opt_id'] if use_option else selected_plan['base_id']

            st.write(f"**選択中: {selected_plan['name']}**")
            st.subheader(f"ご請求額: ¥{final_price:,} / 月")
            
            st.markdown("🔒 **安全な決済のため、Fincodeの決済画面へ移動します**")
            if st.button("お支払い画面へ進む (3Dセキュア対応)"):
                if not FINCODE_API_KEY: st.error("API設定エラー"); st.stop()
                
                with st.spinner("決済ページを準備中..."):
                    f_cust_id = str(user_row.get('fincode_customer_id', ''))
                    if f_cust_id in ["", "nan", "None"]:
                        res = fincode_register_customer(uid)
                        if "errors" in res:
                            error_msg = res["errors"][0]["error_message"]
                            if "既に登録" in error_msg or "exist" in error_msg.lower():
                                f_cust_id = str(uid)
                                update_user_fincode_data(client, uid, fincode_id=f_cust_id)
                            else:
                                st.error("顧客登録エラー"); st.stop()
                        else:
                            f_cust_id = res["id"]
                            update_user_fincode_data(client, uid, fincode_id=f_cust_id)
                    
                    update_user_temp_settings(client, uid, selected_restriction)
                    
                    # デバッグ用関数を使用
                    session_res = fincode_create_subscription_session_debug(f_cust_id, target_plan_id, APP_BASE_URL)
                    
                    if "errors" in session_res:
                        # 画面にエラーJSONが出ているはずなので、stopせずに表示だけする
                        st.error(f"エラー: {session_res['errors'][0]['error_message']}")
                    else:
                        link_url = session_res["link_url"]
                        st.link_button("👉 ここをクリックして決済を完了させる", link_url, type="primary")

        else:
            st.info("利用を開始するには、以下のプランから選択してください。")
            plan_key = st.radio("プラン選択", ["full", "light"], format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
            selected_plan = PLANS[plan_key]
            
            selected_restriction = "all"
            if plan_key == "light":
                st.markdown("👇 **通知を受け取るカテゴリを選択してください**")
                sub_choice = st.radio(
                    "カテゴリ選択", 
                    ["apparel", "not_apparel"], 
                    format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外"
                )
                selected_restriction = sub_choice
            
            st.markdown("---")
            use_option = st.checkbox(f"✨ **キーワード通知オプションを追加する (+¥{OPTION_PRICE:,})**")
            
            final_price = selected_plan['base_price'] + (OPTION_PRICE if use_option else 0)
            target_plan_id = selected_plan['opt_id'] if use_option else selected_plan['base_id']

            st.markdown("---")
            st.write(f"**選択中: {selected_plan['name']}**")
            if plan_key == "light":
                disp_text = "👜 アパレル" if selected_restriction == "apparel" else "📷 アパレル以外"
                st.info(f"選択カテゴリ: {disp_text}")
            
            if use_option:
                st.success(f"オプション適用: あり (+¥{OPTION_PRICE:,})")
            
            st.subheader(f"ご請求額: ¥{final_price:,} / 月")
            
            st.markdown("🔒 **安全な決済のため、Fincodeの決済画面へ移動します**")
            st.caption("※クレジットカード情報はFincodeが安全に管理し、当サイトには保存されません。")
            
            if st.button("お支払い画面へ進む (3Dセキュア対応)"):
                if not FINCODE_API_KEY:
                    st.error("API設定エラー")
                    st.stop()

                with st.spinner("決済ページを準備中..."):
                    f_cust_id = str(user_row.get('fincode_customer_id', ''))
                    if f_cust_id in ["", "nan", "None"]:
                        res = fincode_register_customer(uid)
                        if "errors" in res:
                            error_msg = res["errors"][0]["error_message"]
                            if "既に登録" in error_msg or "exist" in error_msg.lower():
                                f_cust_id = str(uid)
                                update_user_fincode_data(client, uid, fincode_id=f_cust_id)
                            else:
                                st.error("顧客登録エラー"); st.stop()
                        else:
                            f_cust_id = res["id"]
                            update_user_fincode_data(client, uid, fincode_id=f_cust_id)

                    update_user_temp_settings(client, uid, selected_restriction)

                    # デバッグ用関数を使用
                    session_res = fincode_create_subscription_session_debug(f_cust_id, target_plan_id, APP_BASE_URL)
                    
                    if "errors" in session_res:
                        st.error(f"エラー: {session_res['errors'][0]['error_message']}")
                    else:
                        link_url = session_res["link_url"]
                        st.link_button("👉 ここをクリックして決済を完了させる", link_url, type="primary")

    elif menu == "アカウント設定":
        st.subheader("⚙️ アカウント設定")

        with st.expander("🔑 パスワードの変更", expanded=False):
            st.info("セキュリティのため、定期的な変更をおすすめします。")
            with st.form("password_reset_form"):
                current_pw = st.text_input("現在のパスワード", type="password")
                new_pw = st.text_input("新しいパスワード", type="password")
                new_pw_confirm = st.text_input("新しいパスワード（確認）", type="password")
                submit_pw = st.form_submit_button("パスワードを変更する")

            if submit_pw:
                if not current_pw or not new_pw or not new_pw_confirm:
                    st.error("全ての項目を入力してください")
                elif new_pw != new_pw_confirm:
                    st.error("新しいパスワードが一致しません")
                else:
                    current_hash = user_row.get('パスワードハッシュ', '')
                    if hash_password(current_pw) != current_hash:
                        st.error("現在のパスワードが間違っています")
                    else:
                        with st.spinner("更新中..."):
                            suc, msg = update_user_password(client, uid, new_pw)
                            if suc: st.success(msg)
                            else: st.error(msg)
        
        st.markdown("---")
        st.subheader("🛡️ 2段階認証 (2FA)")
        
        if user_secret_key:
            st.success("✅ **2段階認証は現在「有効」です**")
            st.info("解除するには下のボタンを押してください。")
            if st.button("2段階認証を解除する", type="primary"):
                if update_user_secret(client, uid, ""):
                    st.warning("2段階認証を解除しました。")
                    time.sleep(1)
                    st.rerun()
        else:
            st.warning("⚠️ **2段階認証は設定されていません**")
            st.write("設定すると、ログイン時に認証アプリ（Google Authenticatorなど）のコード入力が必要になります。")
            
            if '2fa_setup_secret' not in st.session_state:
                st.session_state['2fa_setup_secret'] = pyotp.random_base32()
            
            secret = st.session_state['2fa_setup_secret']
            
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=uname, issuer_name="MyApp")
            qr_img = qrcode.make(uri)
            
            img_byte_arr = io.BytesIO()
            qr_img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(img_byte_arr, caption="認証アプリでスキャン", width=200)
            with col2:
                st.markdown(
                    f"""
                    1. Google Authenticator等のアプリで左のQRコードをスキャンしてください。
                    2. 表示された6桁のコードを以下に入力して「有効にする」を押してください。
                    
                    **シークレットキー (手入力用):** `{secret}`
                    """
                )
                verify_code = st.text_input("6桁のコード", max_chars=6, key="otp_setup")
                
                if st.button("有効にする"):
                    totp = pyotp.TOTP(secret)
                    if totp.verify(verify_code):
                        if update_user_secret(client, uid, secret):
                            st.success("🎉 2段階認証が有効になりました！")
                            del st.session_state['2fa_setup_secret']
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("設定の保存に失敗しました。")
                    else:
                        st.error("コードが間違っています。もう一度確認してください。")

if __name__ == "__main__":
    main()
