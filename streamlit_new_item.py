import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import json
import time
import requests
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

# ★ プラン設定（FincodeのプランIDと合わせる）
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
#  Fincode API連携関数
# ==========================================
def fincode_register_customer(user_id):
    """顧客を作成する"""
    url = f"{FINCODE_BASE_URL}/customers"
    data = {"id": str(user_id), "description": f"User: {user_id}"}
    response = requests.post(url, json=data, headers=HEADERS)
    return response.json()

def fincode_register_card(customer_id, card_no, expire, security_code, holder_name):
    """カードを登録する"""
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
    """サブスクリプションを開始する"""
    url = f"{FINCODE_BASE_URL}/subscriptions"
    data = {
        "pay_type": "Card",
        "plan_id": plan_id,
        "customer_id": customer_id,
        "start_date": None
    }
    res = requests.post(url, json=data, headers=HEADERS).json()
    if "errors" in res:
        return False, res["errors"][0]["error_message"]
    return True, res["id"]

def fincode_cancel_subscription(subscription_id):
    """サブスクリプションを解約する"""
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
    """ユーザー管理シートの初期化（F列まで確保）"""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            sh.worksheet(USERS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=6)
            # F列: plan_id を追加
            ws.append_row(['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 'subscription_id', 'plan_id']) 
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
            if len(data) < 2:
                return pd.DataFrame(columns=['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id', 'subscription_id', 'plan_id'])
            
            df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
            # 列補完
            for col in ['fincode_customer_id', 'subscription_id', 'plan_id']:
                if col not in df.columns: df[col] = ""
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
    if str(user_id) in users_df['ユーザーID'].values:
        return False, "このユーザーIDは既に登録されています。"
    if str(user_name) in users_df['ユーザー名'].values:
        return False, "このユーザー名は既に使用されています。"
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        hashed_pw = hash_password(password)
        # F列まで空文字で埋める
        sheet.append_row([str(user_id), str(user_name), hashed_pw, "", "", ""])
        get_users_df.clear()
        return True, "登録完了"
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
    """DB上のFincode関連情報を更新する"""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            if fincode_id is not None:
                ws.update_cell(cell.row, 4, fincode_id) # D列
            if subscription_id is not None:
                ws.update_cell(cell.row, 5, subscription_id) # E列
            if plan_id is not None:
                ws.update_cell(cell.row, 6, plan_id) # F列 (追加)
            
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
            st.info("※ DiscordのユーザーIDを入力してください")
            r_id = st.text_input("Discord ID", key="ri")
            r_name = st.text_input("表示名", key="rn")
            r_pass = st.text_input("パスワード", type="password", key="rp")
            if st.button("登録"):
                suc, msg = register_user(client, r_id, r_name, r_pass)
                if suc: st.success(msg)
                else: st.error(msg)
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
    user_row = users_df[users_df['ユーザーID'] == str(uid)].iloc[0]
    
    # 契約状態の確認
    sub_id = str(user_row.get('subscription_id', ''))
    current_plan_id = str(user_row.get('plan_id', ''))
    is_subscribed = (sub_id != "" and sub_id.lower() != "nan" and sub_id.lower() != "none")

    # ---------------------------
    #  メニュー1: 通知設定
    # ---------------------------
    if menu == "通知設定":
        choices_df = get_choices_df(client)
        opts = sorted([f"{r['サイト']} - {r['カテゴリ']}" for _, r in choices_df.drop_duplicates().iterrows() if r['サイト']]) if not choices_df.empty else []
        
        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        display_df = user_df[['検索条件', 'ブランドキーワード']] if '検索条件' in user_df.columns else pd.DataFrame(columns=['検索条件', 'ブランドキーワード'])
        
        st.subheader("📢 通知条件の設定")
        
        # ★ プランによる制限の案内表示（将来的な実装のために表示のみ）
        if is_subscribed:
            if current_plan_id == PLANS["full"]["id"]:
                st.info("💎 **フルプラン契約中**: 全てのカテゴリを設定可能です。")
            elif current_plan_id == PLANS["light"]["id"]:
                st.info("💡 **ライトプラン契約中**: 設定内容にご注意ください。")
        else:
            st.warning("⚠️ プラン未契約です。通知を受け取るには契約が必要です。")

        edited = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, 
                                column_config={"検索条件": st.column_config.SelectboxColumn(options=opts, required=True)})
        
        if st.button("設定を保存", type="primary"):
            save_merged_data(client, full_df, edited, uid)

    # ---------------------------
    #  メニュー2: サブスク契約・解約
    # ---------------------------
    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        
        if is_subscribed:
            # === 契約中（解約画面） ===
            st.success("✅ **現在プラン契約中です**")
            
            # 契約プラン名の表示
            plan_name = "不明なプラン"
            if current_plan_id == PLANS["full"]["id"]:
                plan_name = PLANS["full"]["name"]
            elif current_plan_id == PLANS["light"]["id"]:
                plan_name = PLANS["light"]["name"]
            
            st.write(f"**契約プラン**: {plan_name}")
            st.caption(f"Sub ID: {sub_id} / Plan ID: {current_plan_id}")
            
            st.markdown("---")
            if st.button("プランを解約する"):
                with st.spinner("解約処理中..."):
                    suc, msg = fincode_cancel_subscription(sub_id)
                    if suc:
                        # DBからIDを削除
                        update_user_fincode_data(client, uid, subscription_id="", plan_id="")
                        st.success("解約が完了しました。")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"解約エラー: {msg}")
        else:
            # === 未契約（契約フォーム） ===
            st.info("契約するプランを選択してください。")
            
            # ★ プラン選択ラジオボタン
            plan_key = st.radio(
                "プラン選択",
                ["full", "light"],
                format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['price']:,}/月"
            )
            selected_plan = PLANS[plan_key]
            
            st.write(f"**選択中: {selected_plan['name']}**")
            st.caption(selected_plan['desc'])
            
            with st.form("pay_form"):
                st.write("クレジットカード情報")
                c1, c2 = st.columns(2)
                card_no = c1.text_input("カード番号", max_chars=16, placeholder="半角数字")
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
                            # 3. 選んだプランでサブスク開始
                            suc, res_sub_id = fincode_create_subscription(f_cust_id, selected_plan["id"])
                            if suc:
                                # DBにサブスクIDとプランIDを保存
                                update_user_fincode_data(client, uid, subscription_id=res_sub_id, plan_id=selected_plan["id"])
                                st.balloons()
                                st.success("サブスクリプションを開始しました！")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"契約エラー: {res_sub_id}")

if __name__ == "__main__":
    main()
