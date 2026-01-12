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

# ★ Discord設定 (Secretsから読み込み)
try:
    DISCORD_BOT_TOKEN = st.secrets["discord"]["bot_token"]
    DISCORD_GUILD_ID = st.secrets["discord"]["guild_id"]
except Exception:
    DISCORD_BOT_TOKEN = ""
    DISCORD_GUILD_ID = ""

# ★ プラン設定
PLANS = {
    "full": {
        "name": "フルプラン (アパレル・その他)",
        "id": "plan_9000",
        "price": 9000,
        "desc": "全てのカテゴリを通知します"
    },
    "light": {
        "name": "ライトプラン (片方のみ)",
        "id": "plan_5000",
        "price": 5000,
        "desc": "アパレル または その他のどちらか一方"
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
        st.error("認証ファイルが見つかりません。Secretsの設定を確認してください。")
        return None
    return None

# ==========================================
#  特定商取引法に基づく表記 (審査用)
# ==========================================
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
        | **販売価格** | プラン契約画面に記載 (月額5,000円 / 9,000円) |
        | **商品代金以外の必要料金** | なし（インターネット接続料金はお客様負担） |
        | **支払方法** | クレジットカード決済 |
        | **支払時期** | 初回契約時および毎月同日に請求 |
        | **商品の引渡時期** | 決済完了後、即時利用可能 |
        | **返品・交換** | デジタルコンテンツの性質上、返品・返金には応じられません。解約はいつでもマイページから可能です（次回請求分から停止）。 |
        """)

# ==========================================
#  Discord API連携 (チャンネル自動作成)
# ==========================================
def create_discord_channel_and_webhook(user_discord_id, user_name):
    """
    DiscordユーザーID指定でプライベートチャンネルを作成し、
    Webhook URLを発行して返す
    """
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        return False, "サーバー側のDiscord設定が不足しています"

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # 1. チャンネル作成 (プライベート設定)
    # permission_overwrites: @everyone(guild_id)を拒否, 対象ユーザー(user_discord_id)を許可
    url_create = f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/channels"
    
    # VIEW_CHANNEL (1024) 権限
    payload = {
        "name": f"通知-{user_name}",
        "type": 0, # Text Channel
        "permission_overwrites": [
            {
                "id": DISCORD_GUILD_ID, # @everyone role
                "type": 0, # Role
                "deny": "1024" # VIEW_CHANNEL Deny
            },
            {
                "id": user_discord_id, # Target User
                "type": 1, # Member
                "allow": "1024" # VIEW_CHANNEL Allow
            }
        ]
    }
    
    res = requests.post(url_create, json=payload, headers=headers)
    if res.status_code not in [200, 201]:
        return False, f"チャンネル作成失敗: {res.text}"
    
    channel_data = res.json()
    channel_id = channel_data["id"]

    # 2. Webhook作成
    url_webhook = f"https://discord.com/api/v10/channels/{channel_id}/webhooks"
    webhook_payload = {"name": "新着通知Bot"}
    
    res_wh = requests.post(url_webhook, json=webhook_payload, headers=headers)
    if res_wh.status_code not in [200, 201]:
        return False, f"Webhook作成失敗: {res_wh.text}"
        
    webhook_data = res_wh.json()
    webhook_url = webhook_data["url"]
    
    return True, webhook_url

# ==========================================
#  Fincode API連携関数
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
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=7) # 列数を7に変更
            # ★ チャンネルURL列を追加
            ws.append_row(['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 'subscription_id', 'plan_id', 'チャンネルURL']) 
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
            # カラム定義
            cols = ['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 'subscription_id', 'plan_id', 'チャンネルURL']
            
            if len(data) < 2:
                return pd.DataFrame(columns=cols)
            
            # データフレーム作成（カラム不足時は補完）
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
    
    # 重複チェック
    if str(user_id) in users_df['ユーザーID'].values:
        return False, "このユーザーIDは既に登録されています。"
    if str(user_name) in users_df['ユーザー名'].values:
        return False, "このユーザー名は既に使用されています。"
        
    # ★ Discordチャンネル自動作成
    webhook_url = ""
    try:
        # ユーザーに通知しつつ処理
        with st.spinner("Discordチャンネルを作成中..."):
            success_discord, result_discord = create_discord_channel_and_webhook(user_id, user_name)
            
            if success_discord:
                webhook_url = result_discord
            else:
                # チャンネル作成失敗時の挙動（ここでは登録自体を止めるか、警告を出すか）
                return False, f"Discordチャンネル作成エラー: {result_discord}\nIDが正しいか、Botがサーバーにいるか確認してください。"
    except Exception as e:
        return False, f"Discord連携中にエラーが発生しました: {e}"

    # シートへ保存
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        hashed_pw = hash_password(password)
        # ★ Webhook URLも含めて保存
        sheet.append_row([str(user_id), str(user_name), hashed_pw, "", "", "", webhook_url])
        get_users_df.clear()
        return True, "登録完了！Discordサーバーにあなた専用チャンネルを作成しました。"
    except Exception as e:
        return False, f"登録エラー: {e}"

def login_user(client, login_input, password):
    users_df = get_users_df(client)
    user_row = users_df[
        (users_df['ユーザーID'] == str(login_input)) | 
        (users_df['ユーザー名'] == str(login_input))
    ]
    if user_row.empty:
        return False, "ユーザーが見つかりません。", "", ""
    stored_hash = user_row.iloc[0]['パスワードハッシュ']
    if stored_hash == hash_password(password):
        return True, "ログイン成功", user_row.iloc[0]['ユーザーID'], user_row.iloc[0]['ユーザー名']
    else:
        return False, "パスワードが間違っています。", "", ""

def update_user_fincode_data(client, user_id, fincode_id=None, subscription_id=None, plan_id=None):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            if fincode_id is not None:
                ws.update_cell(cell.row, 4, fincode_id)
            if subscription_id is not None:
                ws.update_cell(cell.row, 5, subscription_id)
            if plan_id is not None:
                ws.update_cell(cell.row, 6, plan_id)
            
            get_users_df.clear()
            return True
    except Exception as e:
        st.error(f"DB更新エラー: {e}")
        return False

# ==========================================
#  通知設定用データ操作
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
        final_cols = ['ユーザーID', '検索条件', 'ブランドキーワード']
        if not data: return pd.DataFrame(columns=final_cols)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        if 'サイト' in df.columns:
            if '検索条件' not in df.columns: df['検索条件'] = df['サイト'] + " - " + df['カテゴリ']
        for col in final_cols:
            if col not in df.columns: df[col] = ""
        return df[final_cols]
    except: return None

def save_merged_data(client, full_df, edited_display_df, user_id):
    try:
        new_rows = []
        for i, row in edited_display_df.iterrows():
            combo = row['検索条件']
            keywords = row['ブランドキーワード']
            if not combo or not isinstance(combo, str): continue
            new_rows.append({'ユーザーID': str(user_id), '検索条件': combo, 'ブランドキーワード': keywords})
        
        save_user_df = pd.DataFrame(new_rows)
        other_users_df = full_df[full_df['ユーザーID'] != str(user_id)]
        
        cols = ['ユーザーID', '検索条件', 'ブランドキーワード']
        for c in cols:
            if c not in save_user_df.columns: save_user_df[c] = ""
            if c not in other_users_df.columns: other_users_df[c] = ""
            
        final_df = pd.concat([other_users_df, save_user_df], ignore_index=True)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        update_data = [final_df.columns.tolist()] + final_df.astype(str).values.tolist()
        sheet.clear()
        sheet.update('A1', update_data)
        load_data.clear()
        st.success(f"✅ 設定を保存しました！（{len(save_user_df)}件）")
        return final_df
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return None

# ==========================================
#  メインアプリケーション
# ==========================================
def main():
    st.title("🔔 通知設定＆サブスク管理")
    client = get_gspread_client()
    if not client: return

    if 'logged_in_user_id' not in st.session_state:
        st.session_state['logged_in_user_id'] = None
        st.session_state['logged_in_user_name'] = None

    # --- ログイン前 ---
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
            st.info("※ DiscordのユーザーIDを入力してください。登録と同時に専用チャンネルを作成します。")
            r_id = st.text_input("Discord ID", key="ri", help="Discordアプリの設定 > 詳細設定 > 開発者モードをONにして、アイコンを右クリックでコピーできます")
            r_name = st.text_input("表示名", key="rn")
            r_pass = st.text_input("パスワード", type="password", key="rp")
            if st.button("登録"):
                if not r_id or not r_name or not r_pass:
                    st.error("全ての項目を入力してください")
                else:
                    suc, msg = register_user(client, r_id, r_name, r_pass)
                    if suc: 
                        st.success(msg)
                        st.balloons()
                    else: 
                        st.error(msg)
        
        # ★★★ 審査用：特定商取引法に基づく表記の表示 ★★★
        show_tokushoho()
        
        st.stop()

    # --- ログイン後 ---
    uid = st.session_state['logged_in_user_id']
    uname = st.session_state['logged_in_user_name']
    
    with st.sidebar:
        st.write(f"User: **{uname}**")
        menu = st.radio("メニュー", ["通知設定", "プラン契約・解約"])
        if st.button("ログアウト"):
            st.session_state['logged_in_user_id'] = None
            st.rerun()

    full_df = load_data(client)
    users_df = get_users_df(client)
    
    # ユーザー情報取得（なければログアウト）
    if users_df[users_df['ユーザーID'] == str(uid)].empty:
        st.error("ユーザー情報が見つかりません")
        st.session_state['logged_in_user_id'] = None
        st.stop()
        
    user_row = users_df[users_df['ユーザーID'] == str(uid)].iloc[0]
    
    sub_id = str(user_row.get('subscription_id', ''))
    current_plan_id = str(user_row.get('plan_id', ''))
    # ★ チャンネルURLを表示してあげる
    channel_url = str(user_row.get('チャンネルURL', ''))
    
    is_subscribed = (sub_id != "" and sub_id.lower() != "nan" and sub_id.lower() != "none")

    if menu == "通知設定":
        choices_df = get_choices_df(client)
        opts = sorted([f"{r['サイト']} - {r['カテゴリ']}" for _, r in choices_df.drop_duplicates().iterrows() if r['サイト']]) if not choices_df.empty else []
        
        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        display_df = user_df[['検索条件', 'ブランドキーワード']] if '検索条件' in user_df.columns else pd.DataFrame(columns=['検索条件', 'ブランドキーワード'])
        
        st.subheader("📢 通知条件の設定")
        if is_subscribed:
            if current_plan_id == PLANS["full"]["id"]: st.info("💎 **フルプラン契約中**")
            elif current_plan_id == PLANS["light"]["id"]: st.info("💡 **ライトプラン契約中**")
            
            # 通知先情報の表示
            with st.expander("📡 あなたの通知チャンネル"):
                if channel_url:
                    st.success("✅ Discord連携済み")
                    st.write("このWebhook URLに通知が届きます（Bot側で自動設定されます）")
                    st.code(channel_url)
                else:
                    st.warning("⚠️ チャンネル情報が登録されていません。管理者に問い合わせてください。")
        else:
            st.warning("⚠️ プラン未契約です")

        edited = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, 
                                column_config={"検索条件": st.column_config.SelectboxColumn(options=opts, required=True)})
        
        if st.button("設定を保存", type="primary"):
            save_merged_data(client, full_df, edited, uid)

    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        
        if is_subscribed:
            st.success("✅ **現在プラン契約中です**")
            plan_name = "不明なプラン"
            if current_plan_id == PLANS["full"]["id"]: plan_name = PLANS["full"]["name"]
            elif current_plan_id == PLANS["light"]["id"]: plan_name = PLANS["light"]["name"]
            st.write(f"**契約プラン**: {plan_name}")
            st.caption(f"Sub ID: {sub_id}")
            
            st.markdown("---")
            if st.button("プランを解約する"):
                with st.spinner("解約処理中..."):
                    suc, msg = fincode_cancel_subscription(sub_id)
                    if suc:
                        update_user_fincode_data(client, uid, subscription_id="", plan_id="")
                        st.success("解約が完了しました。")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"解約エラー: {msg}")
        else:
            st.info("契約するプランを選択してください。")
            plan_key = st.radio("プラン選択", ["full", "light"], format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['price']:,}/月")
            selected_plan = PLANS[plan_key]
            
            st.write(f"**選択中: {selected_plan['name']}**")
            st.caption(selected_plan['desc'])
            
            with st.form("pay_form"):
                st.write("クレジットカード情報")
                c1, c2 = st.columns(2)
                card_no = c1.text_input("カード番号", max_chars=16, placeholder="1234567812345678")
                holder = c2.text_input("名義", placeholder="TARO YAMADA")
                c3, c4 = st.columns(2)
                expire = c3.text_input("有効期限 (YYMM)", max_chars=4, placeholder="2512")
                cvc = c4.text_input("セキュリティコード", type="password", max_chars=4)
                
                submitted = st.form_submit_button(f"¥{selected_plan['price']:,} で定期購読を開始")
            
            if submitted:
                if not (card_no and holder and expire and cvc):
                    st.error("全ての項目を入力してください")
                else:
                    if not FINCODE_API_KEY:
                        st.error("API設定エラー")
                        st.stop()

                    with st.spinner("処理中..."):
                        # 1. 顧客ID
                        f_cust_id = str(user_row.get('fincode_customer_id', ''))
                        if f_cust_id in ["", "nan", "None"]:
                            res = fincode_register_customer(uid)
                            if "errors" in res:
                                st.error(res["errors"][0]["error_message"])
                                st.stop()
                            f_cust_id = res["id"]
                            update_user_fincode_data(client, uid, fincode_id=f_cust_id)

                        # 2. カード登録
                        res_card = fincode_register_card(f_cust_id, card_no, expire, cvc, holder)
                        if "errors" in res_card:
                            st.error(f"カード登録エラー: {res_card['errors'][0]['error_message']}")
                        else:
                            # 3. サブスク開始
                            suc, res_sub, req_data, res_raw = fincode_create_subscription(f_cust_id, selected_plan["id"])
                            if suc:
                                update_user_fincode_data(client, uid, subscription_id=res_sub, plan_id=selected_plan["id"])
                                st.balloons()
                                st.success("サブスクリプションを開始しました！")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"契約エラー: {res_sub}")
                                with st.expander("🛠 デバッグ用ログ (詳細)"):
                                    st.write("▼ 送信データ (Request)")
                                    st.json(req_data)
                                    st.write("▼ 受信データ (Response)")
                                    st.json(res_raw)

if __name__ == "__main__":
    main()
