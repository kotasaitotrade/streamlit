import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError

# ==========================================
#  設定・定数
# ==========================================
CREDENTIALS_PATH = 'google_credentials.json'
TOKEN_PATH = 'gspread_token.json'

SPREADSHEET_ID = "1Y8VEVn95FOp5ELLtBiuUrB9m4S3qDSiX50G6aB88vnk"
TARGET_SHEET_NAME = "ユーザー設定"
USERS_SHEET_NAME = "ユーザー管理"
CHOICES_SHEET_NAME = "管理"

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
#  Secrets & 認証処理
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
#  Discord API連携
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
#  Fincode API
# ==========================================
def fincode_register_customer(user_id):
    url = f"{FINCODE_BASE_URL}/customers"
    data = {"id": str(user_id), "description": f"User: {user_id}"}
    response = requests.post(url, json=data, headers=HEADERS)
    return response.json()

def fincode_register_card(customer_id, card_no, expire, security_code, holder_name):
    url = f"{FINCODE_BASE_URL}/customers/{customer_id}/cards"
    data = {
        "default_flag": "1",
        "token": None,
        "card_no": card_no,
        "expire": expire,
        "security_code": security_code,
        "holder_name": holder_name
    }
    response = requests.post(url, json=data, headers=HEADERS)
    return response.json()

def fincode_create_subscription(customer_id, plan_id):
    url = f"{FINCODE_BASE_URL}/subscriptions"
    JST = timezone(timedelta(hours=9))
    today_str = datetime.now(JST).strftime('%Y/%m/%d')
    data = {
        "pay_type": "Card",
        "plan_id": plan_id,
        "customer_id": customer_id,
        "start_date": today_str
    }
    res = requests.post(url, json=data, headers=HEADERS).json()
    if "errors" in res:
        return False, res["errors"][0]["error_message"], data, res
    return True, res["id"], data, res

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

def fincode_cancel_subscription(subscription_id):
    url = f"{FINCODE_BASE_URL}/subscriptions/{subscription_id}"
    res = requests.delete(url, headers=HEADERS).json()
    if "errors" in res:
        return False, res["errors"][0]["error_message"]
    return True, "解約しました"

# ==========================================
#  ユーザー管理・DB操作
# ==========================================
def hash_password(password):
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def ensure_users_sheet(client):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            sh.worksheet(USERS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=8)
            ws.append_row(['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 'subscription_id', 'plan_id', 'チャンネルURL', '制限設定']) 
    except Exception as e:
        st.error(f"ユーザーDB初期化エラー: {e}")

@st.cache_data(ttl=60)
def get_users_df(_client):
    ensure_users_sheet(_client)
    max_retries = 3
    for i in range(max_retries):
        try:
            sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
            data = sheet.get_all_values()
            cols = ['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 'subscription_id', 'plan_id', 'チャンネルURL', '制限設定']
            
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
        sheet.append_row([str(user_id), str(user_name), hashed_pw, "", "", "", webhook_url, ""])
        get_users_df.clear()
        return True, "登録完了"
    except Exception as e: return False, f"保存エラー: {e}"

def login_user(client, login_input, password):
    users_df = get_users_df(client)
    user_row = users_df[(users_df['ユーザーID'] == str(login_input)) | (users_df['ユーザー名'] == str(login_input))]
    if user_row.empty: return False, "ユーザーなし", "", ""
    if user_row.iloc[0]['パスワードハッシュ'] == hash_password(password):
        return True, "成功", user_row.iloc[0]['ユーザーID'], user_row.iloc[0]['ユーザー名']
    else: return False, "パスワード違い", "", ""

def update_user_fincode_data(client, user_id, fincode_id=None, subscription_id=None, plan_id=None, restriction_type=None):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            if fincode_id is not None: ws.update_cell(cell.row, 4, fincode_id)
            if subscription_id is not None: ws.update_cell(cell.row, 5, subscription_id)
            if plan_id is not None: ws.update_cell(cell.row, 6, plan_id)
            if restriction_type is not None: ws.update_cell(cell.row, 8, restriction_type)
            
            get_users_df.clear()
            return True
    except Exception as e:
        st.error(f"DB更新エラー: {e}")
        return False

# ==========================================
#  通知設定用
# ==========================================
@st.cache_data(ttl=60)
def get_choices_df(_client):
    try:
        sh = _client.open_by_key(SPREADSHEET_ID)
        try: sheet = sh.worksheet(CHOICES_SHEET_NAME)
        # ★ 「種類」列を追加して読み込む
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

# ★ カテゴリ判定と選択肢取得を行うヘルパー関数
def get_allowed_options(client, restriction_type):
    choices_df = get_choices_df(client)
    allowed = []
    if choices_df.empty: return []
    
    for _, row in choices_df.drop_duplicates().iterrows():
        site = str(row.get('サイト', '')).strip()
        cat = str(row.get('カテゴリ', '')).strip()
        # ★ シートの「種類」列を厳密に読み取る
        kind = str(row.get('種類', '')).strip()
        
        if not site: continue
        combo_name = f"{site} - {cat}"
        
        item_type = 'other'
        if kind == 'アパレル': item_type = 'apparel'
        elif kind == 'アパレル以外': item_type = 'not_apparel'
        
        # 判定
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

# ★ save_merged_data にプラン判定ロジックを追加
def save_merged_data(client, full_df, edited_display_df, user_id, restriction_type):
    try:
        # 1. キーワード数チェック
        is_valid, err_msg = validate_keywords(edited_display_df)
        if not is_valid:
            st.error(err_msg)
            return None
        
        # 2. ★プラン整合性チェック (バックエンドバリデーション)
        allowed_opts = get_allowed_options(client, restriction_type)
        for i, row in edited_display_df.iterrows():
            combo = row['検索条件']
            if combo and combo not in allowed_opts:
                # ユーザーへのメッセージ
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
#  メイン
# ==========================================
def main():
    st.title("🔔 通知設定＆サブスク管理")
    client = get_gspread_client()
    if not client: return

    if 'logged_in_user_id' not in st.session_state:
        st.session_state['logged_in_user_id'] = None
        st.session_state['logged_in_user_name'] = None

    if st.session_state['logged_in_user_id'] is None:
        tab1, tab2 = st.tabs(["🔑 ログイン", "✨ 新規登録"])
        with tab1:
            l_input = st.text_input("ID / 名前", key="li")
            l_pass = st.text_input("パスワード", type="password", key="lp")
            if st.button("ログイン", type="primary"):
                get_users_df.clear()
                suc, msg, uid, uname = login_user(client, l_input, l_pass)
                if suc:
                    st.session_state['logged_in_user_id'] = uid
                    st.session_state['logged_in_user_name'] = uname
                    st.rerun()
                else: st.error(msg)
        with tab2:
            st.info("DiscordユーザーIDを入力してください")
            r_id = st.text_input("Discord ID", key="ri")
            r_name = st.text_input("表示名", key="rn")
            r_pass = st.text_input("パスワード", type="password", key="rp")
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
    restriction_type = str(user_row.get('制限設定', 'all'))
    if not restriction_type: restriction_type = 'all'

    is_subscribed = (sub_id != "" and sub_id.lower() != "nan" and sub_id.lower() != "none")

    opt_ids = [PLANS["full"]["opt_id"], PLANS["light"]["opt_id"]]
    has_option = (current_plan_id in opt_ids)

    with st.sidebar:
        st.write(f"User: **{uname}**")
        menu = st.radio("メニュー", ["通知設定", "プラン契約・解約"])
        if st.button("ログアウト"):
            st.session_state['logged_in_user_id'] = None
            st.rerun()

    full_df = load_data(client)

    if menu == "通知設定":
        st.subheader("📢 通知条件の設定")

        if not is_subscribed:
            st.error("⚠️ この機能を利用するにはプラン契約が必要です")
            st.info("左側のメニュー「プラン契約・解約」から、プランへの加入手続きを行ってください。")
            st.stop()

        # ★ 選択肢の取得 (ヘルパー関数を利用)
        allowed_opts = get_allowed_options(client, restriction_type)
        
        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        display_df = user_df[['検索条件', 'キーワード']] if '検索条件' in user_df.columns else pd.DataFrame(columns=['検索条件', 'キーワード'])
        
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
            column_config={
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
            # ★ 制限タイプを渡してバリデーションさせる
            save_merged_data(client, full_df, edited, uid, restriction_type)

    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        
        if is_subscribed:
            st.success("✅ **現在プラン契約中です**")
            
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
                    suc, msg = fincode_cancel_subscription(sub_id)
                    if suc:
                        update_user_fincode_data(client, uid, subscription_id="", plan_id="", restriction_type="")
                        st.success("解約が完了しました。")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"解約エラー: {msg}")

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
            
            st.caption("""
            **【オプション機能説明】**
            サイトから抽出した **商品名、ブランド、型番** の中に、設定したキーワード（カンマ区切りで最大20単語）と一致する文字列がある商品だけを通知するフィルタリング機能です。
            
            * ✅ **チェックあり:** キーワードにヒットした商品のみ通知されます。
            * ⬜ **チェックなし:** カテゴリ内の新着商品はすべて通知されます。
            """)

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
            
            with st.form("pay_form"):
                st.write("クレジットカード情報")
                c1, c2 = st.columns(2)
                card_no = c1.text_input("カード番号", max_chars=16, placeholder="1234567812345678")
                holder = c2.text_input("名義", placeholder="TARO YAMADA")
                c3, c4 = st.columns(2)
                expire = c3.text_input("有効期限 (YYMM)", max_chars=4, placeholder="2512")
                cvc = c4.text_input("セキュリティコード", type="password", max_chars=4)
                
                submitted = st.form_submit_button(f"¥{final_price:,} で定期購読を開始")
            
            if submitted:
                if not (card_no and holder and expire and cvc):
                    st.error("全ての項目を入力してください")
                else:
                    if not FINCODE_API_KEY:
                        st.error("API設定エラー")
                        st.stop()

                    with st.spinner("処理中..."):
                        f_cust_id = str(user_row.get('fincode_customer_id', ''))
                        if f_cust_id in ["", "nan", "None"]:
                            res = fincode_register_customer(uid)
                            if "errors" in res:
                                error_msg = res["errors"][0]["error_message"]
                                if "既に登録" in error_msg or "exist" in error_msg.lower():
                                    f_cust_id = str(uid)
                                    update_user_fincode_data(client, uid, fincode_id=f_cust_id)
                                else:
                                    st.error(error_msg)
                                    st.stop()
                            else:
                                f_cust_id = res["id"]
                                update_user_fincode_data(client, uid, fincode_id=f_cust_id)

                        res_card = fincode_register_card(f_cust_id, card_no, expire, cvc, holder)
                        if "errors" in res_card:
                            st.error(f"カード登録エラー: {res_card['errors'][0]['error_message']}")
                        else:
                            suc, res_sub, req_data, res_raw = fincode_create_subscription(f_cust_id, target_plan_id)
                            if suc:
                                update_user_fincode_data(client, uid, subscription_id=res_sub, plan_id=target_plan_id, restriction_type=selected_restriction)
                                st.balloons()
                                st.success("サブスクリプションを開始しました！")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"契約エラー: {res_sub}")

if __name__ == "__main__":
    main()
