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

# ★ プラン設定（FincodeのプランIDに合わせて修正してください）
OPTION_PRICE = 2000
PLANS = {
    "full": {
        "name": "フルプラン (全て)",
        "desc": "アパレル・その他の全てのカテゴリを選択可能",
        "type": "all",
        "base_price": 9000,
        "base_id": "plan_9000",      # Fincodeの9000円プランID
        "opt_id": "plan_11000"       # ★Fincodeで作った11000円プランID
    },
    "light": {
        "name": "ライトプラン (片方のみ)",
        "desc": "「アパレル」または「それ以外」のどちらか一方のみ選択可能",
        "type": "select",
        "base_price": 5000,
        "base_id": "plan_5000",      # Fincodeの5000円プランID
        "opt_id": "plan_7000"        # ★Fincodeで作った7000円プランID
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
        except: return pd.DataFrame(columns=['サイト', 'カテゴリ'])
        data = sheet.get_all_values()
        if len(data) < 2: return pd.DataFrame(columns=['サイト', 'カテゴリ'])
        return pd.DataFrame(data[1:], columns=data[0]).astype(str)
    except: return pd.DataFrame(columns=['サイト', 'カテゴリ'])

@st.cache_data(ttl=60)
def load_data(_client):
    try:
        sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        data = sheet.get_all_values()
        # ★ キーワード列の名前変更
        final_cols = ['ユーザーID', '検索条件', 'キーワード']
        if not data: return pd.DataFrame(columns=final_cols)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        if 'サイト' in df.columns:
            if '検索条件' not in df.columns: df['検索条件'] = df['サイト'] + " - " + df['カテゴリ']
        
        # 旧カラム「ブランドキーワード」がある場合の移行処理（読み込み時）
        if 'ブランドキーワード' in df.columns and 'キーワード' not in df.columns:
            df['キーワード'] = df['ブランドキーワード']
            
        for col in final_cols:
            if col not in df.columns: df[col] = ""
        return df[final_cols]
    except: return None

def validate_keywords(df):
    """キーワードが10個以内かチェック"""
    for index, row in df.iterrows():
        kws = str(row['キーワード']).replace('、', ',').split(',')
        kws = [k for k in kws if k.strip()]
        if len(kws) > 10:
            return False, f"エラー: {row['検索条件']} のキーワードが多すぎます（最大10単語まで）"
    return True, ""

def save_merged_data(client, full_df, edited_display_df, user_id):
    try:
        # バリデーション
        is_valid, err_msg = validate_keywords(edited_display_df)
        if not is_valid:
            st.error(err_msg)
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

def get_category_type(row_series):
    row_text = " ".join([str(v) for v in row_series.values])
    if "アパレル以外" in row_text: return "not_apparel"
    elif "アパレル" in row_text: return "apparel"
    else: return "not_apparel"

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

    # オプション加入判定（オプション込みIDのリストに含まれているか）
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

        choices_df = get_choices_df(client)
        
        allowed_opts = []
        if not choices_df.empty:
            for _, row in choices_df.drop_duplicates().iterrows():
                combo_name = f"{row['サイト']} - {row['カテゴリ']}"
                cat_type = get_category_type(row)
                if restriction_type == 'all': allowed_opts.append(combo_name)
                elif restriction_type == cat_type: allowed_opts.append(combo_name)
        allowed_opts = sorted(allowed_opts)

        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        display_df = user_df[['検索条件', 'キーワード']] if '検索条件' in user_df.columns else pd.DataFrame(columns=['検索条件', 'キーワード'])
        
        # プラン情報の表示
        plan_display_name = "プラン不明"
        if current_plan_id.startswith(PLANS["full"]["base_id"]) or current_plan_id == PLANS["full"]["opt_id"]:
             st.info("💎 **フルプラン契約中**")
        elif current_plan_id.startswith(PLANS["light"]["base_id"]) or current_plan_id == PLANS["light"]["opt_id"]:
             st.info("💡 **ライトプラン契約中**")
             r_text = "👜 アパレルのみ" if restriction_type == "apparel" else "📷 アパレル以外のみ"
             st.caption(f"選択可能カテゴリ: {r_text}")

        # オプション情報の表示
        if has_option:
            st.success("✅ **キーワード通知オプション: 有効**")
            st.caption("商品名、ブランド、型番のいずれかにキーワードが含まれる場合に通知します。（カンマ区切りで複数指定可）")
        else:
            st.warning("🔒 **キーワード通知オプション: 無効**")
            st.caption("この機能を利用するには、プラン契約・変更画面でオプションを追加してください。")

        with st.expander("📡 あなたの通知チャンネル"):
            if channel_url:
                st.success("✅ Discord連携済み")
                st.code(channel_url)
            else:
                st.warning("⚠️ チャンネル情報が登録されていません。")

        # データエディタ (オプション未加入ならキーワード列を編集不可に)
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
                    "キーワード (最大10個)",
                    disabled=(not has_option), # オプションなしなら編集不可
                    help="カンマ(,)区切りで入力。商品名・ブランド・型番のいずれかに一致したら通知。"
                )
            }
        )
        
        if st.button("設定を保存", type="primary"):
            save_merged_data(client, full_df, edited, uid)

    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        
        if is_subscribed:
            st.success("✅ **現在プラン契約中です**")
            # プラン名の解決
            plan_name = "不明なプラン"
            
            # フルプラン判定
            if current_plan_id == PLANS["full"]["base_id"]: plan_name = PLANS["full"]["name"]
            elif current_plan_id == PLANS["full"]["opt_id"]: plan_name = f"{PLANS['full']['name']} + オプション"
            # ライトプラン判定
            elif current_plan_id == PLANS["light"]["base_id"]: plan_name = PLANS["light"]["name"]
            elif current_plan_id == PLANS["light"]["opt_id"]: plan_name = f"{PLANS['light']['name']} + オプション"

            st.write(f"**契約プラン**: {plan_name}")
            
            if "ライト" in plan_name:
                 r_text = "👜 アパレルのみ" if restriction_type == "apparel" else "📷 アパレル以外のみ"
                 st.write(f"**選択カテゴリ**: {r_text}")
            
            st.caption(f"Sub ID: {sub_id}")
            
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
            
            # --- ライトプランの制限選択 ---
            selected_restriction = "all"
            if plan_key == "light":
                st.markdown("👇 **通知を受け取るカテゴリを選択してください**")
                sub_choice = st.radio(
                    "カテゴリ選択", 
                    ["apparel", "not_apparel"], 
                    format_func=lambda x: "👜 アパレル" if x == "apparel" else "📷 アパレル以外"
                )
                selected_restriction = sub_choice
            
            # --- ★ オプション選択 ---
            st.markdown("---")
            use_option = st.checkbox(f"✨ **キーワード通知オプションを追加する (+¥{OPTION_PRICE:,})**")
            if use_option:
                st.caption("✅ 指定したキーワード（商品名・ブランド・型番）が含まれる商品だけを通知できます。")
            else:
                st.caption("通常のカテゴリ通知のみ行います。")
            
            # --- 合計金額計算 ---
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
                                st.error(res["errors"][0]["error_message"])
                                st.stop()
                            f_cust_id = res["id"]
                            update_user_fincode_data(client, uid, fincode_id=f_cust_id)

                        res_card = fincode_register_card(f_cust_id, card_no, expire, cvc, holder)
                        if "errors" in res_card:
                            st.error(f"カード登録エラー: {res_card['errors'][0]['error_message']}")
                        else:
                            # ★ 計算済みの target_plan_id を使用
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
