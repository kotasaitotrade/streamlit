import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import json
import time
import requests  # 追加: API通信用
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError

# --- 設定 ---
CREDENTIALS_PATH = 'google_credentials.json'
TOKEN_PATH = 'gspread_token.json'

SPREADSHEET_ID = "1Y8VEVn95FOp5ELLtBiuUrB9m4S3qDSiX50G6aB88vnk"

# シート名の設定
TARGET_SHEET_NAME = "ユーザー設定"
USERS_SHEET_NAME = "ユーザー管理"
CHOICES_SHEET_NAME = "管理" # 選択肢マスタ

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

st.set_page_config(page_title="通知設定マネージャー", layout="wide")

# --- Secrets処理 ---
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

# --- Fincode設定 (Secretsから読み込み) ---
try:
    FINCODE_API_KEY = st.secrets["fincode"]["api_key"]
    FINCODE_BASE_URL = st.secrets["fincode"]["base_url"]
except Exception:
    # 設定がない場合のエラーハンドリング（アプリが落ちないようにダミーを入れる）
    FINCODE_API_KEY = ""
    FINCODE_BASE_URL = ""

HEADERS = {
    "Authorization": f"Bearer {FINCODE_API_KEY}",
    "Content-Type": "application/json"
}

# --- 認証関連 ---
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

# --- Fincode API連携関数 ---
def fincode_register_customer(user_id):
    """Fincode上に顧客を作成する"""
    url = f"{FINCODE_BASE_URL}/customers"
    data = {
        "id": str(user_id),
        "description": f"User: {user_id}"
    }
    # 既に存在する場合のエラーハンドリングは簡易的
    response = requests.post(url, json=data, headers=HEADERS)
    return response.json()

def fincode_register_card(customer_id, card_no, expire, security_code, holder_name):
    """顧客にカードを登録する"""
    url = f"{FINCODE_BASE_URL}/customers/{customer_id}/cards"
    data = {
        "default_flag": "1",
        "token": None, # 本番環境ではJSでトークン化することを推奨
        "card_no": card_no,
        "expire": expire,
        "security_code": security_code,
        "holder_name": holder_name
    }
    response = requests.post(url, json=data, headers=HEADERS)
    return response.json()

def fincode_execute_payment(customer_id, amount):
    """登録済みカードで決済を実行する"""
    # 1. 決済作成
    url_create = f"{FINCODE_BASE_URL}/payments"
    data_create = {
        "pay_type": "Card",
        "job_code": "CAPTURE",
        "amount": amount,
        "customer_id": customer_id
    }
    res_create = requests.post(url_create, json=data_create, headers=HEADERS).json()
    
    if "errors" in res_create:
        return False, res_create["errors"][0]["error_message"]
    
    access_id = res_create.get("access_id")
    payment_id = res_create.get("id")

    if not access_id or not payment_id:
        return False, "決済IDの取得に失敗しました"

    # 2. 決済実行
    url_exec = f"{FINCODE_BASE_URL}/payments/{payment_id}"
    data_exec = {
        "access_id": access_id,
        "pay_type": "Card",
        "method": "1"
    }
    res_exec = requests.put(url_exec, json=data_exec, headers=HEADERS).json()
    
    if "errors" in res_exec:
        return False, res_exec["errors"][0]["error_message"]
        
    return True, "決済が完了しました"

# --- ユーザー管理 ---
def hash_password(password):
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def ensure_users_sheet(client):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            sh.worksheet(USERS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=4)
            # D列に fincode_customer_id を追加
            ws.append_row(['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id']) 
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
                return pd.DataFrame(columns=['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id'])
            
            # ヘッダーとデータを取得
            df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
            
            # fincode_customer_idカラムがない場合の互換性処理
            if 'fincode_customer_id' not in df.columns:
                df['fincode_customer_id'] = ""
                
            return df
        except APIError as e:
            if "429" in str(e) and i < max_retries - 1:
                time.sleep(2 ** i)
                continue
            st.error(f"ユーザー情報取得エラー: {e}")
            return pd.DataFrame(columns=['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id'])
        except Exception as e:
            st.error(f"エラー: {e}")
            return pd.DataFrame(columns=['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'fincode_customer_id'])

def register_user(client, user_id, user_name, password):
    get_users_df.clear() # キャッシュクリア
    users_df = get_users_df(client)
    if str(user_id) in users_df['ユーザーID'].values:
        return False, "このユーザーIDは既に登録されています。"
    if str(user_name) in users_df['ユーザー名'].values:
        return False, "このユーザー名は既に使用されています。"
    
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        hashed_pw = hash_password(password)
        # 4列目は空文字で登録
        sheet.append_row([str(user_id), str(user_name), hashed_pw, ""])
        get_users_df.clear()
        return True, "登録が完了しました。ログインしてください。"
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
        user_id = user_row.iloc[0]['ユーザーID']
        user_name = user_row.iloc[0]['ユーザー名']
        return True, "ログイン成功", user_id, user_name
    else:
        return False, "パスワードが間違っています。", "", ""

def update_user_fincode_id(client, user_id, fincode_id):
    """ユーザー管理シートにFincode IDを書き込む"""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(user_id))
        if cell:
            # D列(4列目)にIDを保存
            ws.update_cell(cell.row, 4, fincode_id)
            get_users_df.clear()
            return True
    except Exception as e:
        st.error(f"DB更新エラー: {e}")
        return False

# --- 管理シート（選択肢）の取得 ---
@st.cache_data(ttl=60)
def get_choices_df(_client):
    max_retries = 3
    for i in range(max_retries):
        try:
            try:
                sh = _client.open_by_key(SPREADSHEET_ID)
                sheet = sh.worksheet(CHOICES_SHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet(title=CHOICES_SHEET_NAME, rows=100, cols=2)
                ws.append_row(['サイト', 'カテゴリ'])
                ws.append_row(['メルカリ', 'バッグ'])
                sheet = ws

            data = sheet.get_all_values()
            if len(data) < 2:
                return pd.DataFrame(columns=['サイト', 'カテゴリ'])
            
            return pd.DataFrame(data[1:], columns=data[0]).astype(str)
            
        except APIError as e:
            if "429" in str(e) and i < max_retries - 1:
                time.sleep(2 ** i)
                continue
            st.error(f"管理シート読み込みエラー(API制限): {e}")
            return pd.DataFrame(columns=['サイト', 'カテゴリ'])
        except Exception as e:
            st.error(f"管理シート読み込みエラー: {e}")
            return pd.DataFrame(columns=['サイト', 'カテゴリ'])

# --- 設定データの読み込み（自動移行機能付き） ---
@st.cache_data(ttl=60)
def load_data(_client):
    max_retries = 3
    for i in range(max_retries):
        try:
            sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
            data = sheet.get_all_values()
            
            final_cols = ['ユーザーID', '検索条件', 'ブランドキーワード']

            if not data:
                return pd.DataFrame(columns=final_cols)
            
            headers = data[0]
            rows = data[1:]
            df = pd.DataFrame(rows, columns=headers).astype(str)
            
            # --- 自動移行ロジック ---
            if 'サイト' in df.columns and 'カテゴリ' in df.columns:
                if '検索条件' not in df.columns:
                    df['検索条件'] = df['サイト'] + " - " + df['カテゴリ']
                df = df.drop(columns=['サイト', 'カテゴリ'], errors='ignore')
            
            for col in final_cols:
                if col not in df.columns:
                    df[col] = ""
            
            return df[final_cols]

        except APIError as e:
            if "429" in str(e) and i < max_retries - 1:
                time.sleep(2 ** i)
                continue
            st.error(f"データ読み込みエラー(API制限): {e}")
            return None
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")
            return None

# --- データ保存処理 ---
def save_merged_data(client, full_df, edited_display_df, user_id):
    try:
        new_rows = []
        error_rows = False
        
        for i, row in edited_display_df.iterrows():
            combo = row['検索条件']
            keywords = row['ブランドキーワード']
            
            if not combo or not isinstance(combo, str):
                if combo or keywords: 
                    st.warning(f"⚠️ 行 No.{i+1}: 検索条件が無効です。保存されません。")
                    error_rows = True
                continue

            new_rows.append({
                'ユーザーID': str(user_id),
                '検索条件': combo,
                'ブランドキーワード': keywords
            })

        if error_rows:
            st.error("入力内容に不備がある行は無視されました。")
        
        if new_rows:
            save_user_df = pd.DataFrame(new_rows)
        else:
            save_user_df = pd.DataFrame(columns=['ユーザーID', '検索条件', 'ブランドキーワード'])

        other_users_df = full_df[full_df['ユーザーID'] != str(user_id)]
        
        cols = ['ユーザーID', '検索条件', 'ブランドキーワード']
        for c in cols:
            if c not in save_user_df.columns: save_user_df[c] = ""
            if c not in other_users_df.columns: other_users_df[c] = ""
            
        save_user_df = save_user_df.reindex(columns=cols)
        other_users_df = other_users_df.reindex(columns=cols)
        
        final_df = pd.concat([other_users_df, save_user_df], ignore_index=True)
        
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        update_data = [final_df.columns.tolist()] + final_df.astype(str).values.tolist()
        
        sheet.clear()
        
        try:
            sheet.update(values=update_data, range_name='A1')
        except TypeError:
            sheet.update('A1', update_data)
        
        load_data.clear() # キャッシュクリア
        
        st.success(f"✅ 設定を保存しました！（{len(save_user_df)}件）")
        return final_df

    except Exception as e:
        st.error(f"保存エラー: {e}")
        if "403" in str(e):
            st.error("権限エラー: アカウントに編集権限がありません。")
        return None

# --- メイン画面 ---
def main():
    st.title("🔔 自動通知 ユーザー設定管理")
    
    client = get_gspread_client()
    if not client:
        return

    if 'logged_in_user_id' not in st.session_state:
        st.session_state['logged_in_user_id'] = None
        st.session_state['logged_in_user_name'] = None

    # --- ログイン前 ---
    if st.session_state['logged_in_user_id'] is None:
        tab1, tab2 = st.tabs(["🔑 ログイン", "✨ 新規登録"])
        
        with tab1:
            st.subheader("ログイン")
            l_input = st.text_input("ユーザーID または ユーザー名", key="login_input")
            l_pass = st.text_input("パスワード", type="password", key="login_pass")
            if st.button("ログイン", type="primary"):
                if l_input and l_pass:
                    get_users_df.clear()
                    success, msg, u_id, u_name = login_user(client, l_input, l_pass)
                    if success:
                        st.session_state['logged_in_user_id'] = u_id
                        st.session_state['logged_in_user_name'] = u_name
                        st.success(f"{msg} ようこそ {u_name} さん")
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("入力してください")

        with tab2:
            st.subheader("新規登録")
            st.info("※ 通知を送るためにDiscordのユーザーID（数字の羅列）が必要です。")
            
            with st.expander("❓ DiscordユーザーIDの取得方法がわからない方はこちら"):
                st.markdown("""
                DiscordのIDを取得するには「開発者モード」をONにする必要があります。
                1. **設定を開く**: 左下の歯車アイコン（ユーザー設定）をクリック
                2. **詳細設定**: 左メニューの「アプリの設定」カテゴリにある「詳細設定」をクリック
                3. **開発者モードON**: 「開発者モード」のスイッチを **ON** にする
                4. **IDをコピー**: 
                    * 自分のアイコン（左下の名前など）を **右クリック**
                    * メニューの一番下にある **「ユーザーIDをコピー」** をクリック
                5. コピーした数字（例: `123456789012345678`）を下の入力欄に貼り付けてください。
                """)

            r_id = st.text_input("DiscordユーザーID (必須)", key="reg_id", help="開発者モードをONにして、アイコン右クリックでコピーできます")
            r_name = st.text_input("ユーザー名 (表示用)", key="reg_name")
            r_pass = st.text_input("パスワード", type="password", key="reg_pass")
            r_pass_conf = st.text_input("パスワード(確認)", type="password", key="reg_pass_conf")
            
            if st.button("登録する"):
                if r_id and r_name and r_pass and r_pass_conf:
                    if r_pass != r_pass_conf:
                        st.error("パスワードが一致しません")
                    else:
                        success, msg = register_user(client, r_id, r_name, r_pass)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
                else:
                    st.warning("全ての項目を入力してください")
        st.stop()

    # --- ログイン後 ---
    current_user_id = st.session_state['logged_in_user_id']
    current_user_name = st.session_state['logged_in_user_name']
    
    with st.sidebar:
        st.write(f"ユーザー: **{current_user_name}**")
        
        # ★ メニューの切り替え
        menu = st.radio("メニュー", ["通知設定", "プラン契約・決済"])

        st.caption(f"ID: {current_user_id}")
        if st.button("ログアウト"):
            st.session_state['logged_in_user_id'] = None
            st.session_state['logged_in_user_name'] = None
            st.rerun()

    full_df = load_data(client)
    if full_df is None:
        return

    # =================================================
    # 通知設定画面
    # =================================================
    if menu == "通知設定":
        # 管理シートから選択肢を取得
        choices_df = get_choices_df(client)
        if not choices_df.empty:
            valid_pairs = choices_df[['サイト', 'カテゴリ']].drop_duplicates()
            valid_options = sorted([
                f"{r['サイト']} - {r['カテゴリ']}" 
                for _, r in valid_pairs.iterrows() 
                if r['サイト'] and r['カテゴリ']
            ])
        else:
            valid_options = []

        user_df = full_df[full_df['ユーザーID'] == str(current_user_id)].copy()

        if '検索条件' in user_df.columns:
            display_df = user_df[['検索条件', 'ブランドキーワード']].copy()
        else:
            display_df = pd.DataFrame(columns=['検索条件', 'ブランドキーワード'])

        display_df.index = range(1, len(display_df) + 1)

        st.markdown(f"### {current_user_name} さんの通知設定")
        st.info(f"📢 **ここに登録した条件に一致する商品が見つかると、あなたのDiscord ID ({current_user_id}) 宛にメンション通知が届きます。**")

        if not valid_options:
            st.warning("⚠️ 「管理」シートに選択肢がありません。データを確認してください。")

        column_config = {
            "_index": st.column_config.NumberColumn("No.", disabled=True),
            "検索条件": st.column_config.SelectboxColumn(
                "検索条件 (サイト - カテゴリ)",
                options=valid_options,
                required=True,
                width="medium",
            ),
            "ブランドキーワード": st.column_config.TextColumn(
                "ブランドキーワード",
                help="空欄ならカテゴリ全通知"
            ),
        }

        edited_display_df = st.data_editor(
            display_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config=column_config,
            key="user_editor",
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("💾 変更を保存", type="primary"):
                valid_entries = edited_display_df[edited_display_df['検索条件'].notna() & (edited_display_df['検索条件'] != "")]
                if valid_entries['検索条件'].duplicated().any():
                    duplicates = valid_entries[valid_entries['検索条件'].duplicated()]['検索条件'].unique()
                    st.error(f"⚠️ 重複エラー: 以下を1つにまとめてください。\n\n" + ", ".join(duplicates))
                else:
                    new_full_df = save_merged_data(client, full_df, edited_display_df, current_user_id)
                    if new_full_df is not None:
                        st.session_state.df = new_full_df
                        st.rerun()

        with col2:
            if st.button("🔄 最新データを再読み込み"):
                load_data.clear()
                get_choices_df.clear()
                get_users_df.clear()
                st.rerun()

    # =================================================
    # 決済画面
    # =================================================
    elif menu == "プラン契約・決済":
        st.markdown("### 💳 プラン契約")
        st.info("月額プランの支払いに使用するクレジットカードを登録・決済します。")
        
        # 簡易的な決済フォーム
        with st.form("payment_form"):
            col_card1, col_card2 = st.columns(2)
            with col_card1:
                card_no = st.text_input("カード番号", max_chars=16, placeholder="半角数字のみ (ハイフンなし)")
            with col_card2:
                holder = st.text_input("カード名義", placeholder="TARO YAMADA")
            
            col_date, col_cvc = st.columns(2)
            with col_date:
                expire = st.text_input("有効期限 (YYMM)", max_chars=4, placeholder="例: 2512 (2025年12月)")
            with col_cvc:
                cvc = st.text_input("セキュリティコード", type="password", max_chars=4)
            
            amount = 1000  # 決済金額（必要に応じて変更してください）
            st.write(f"**決済金額: ¥{amount}**")
            
            submit_payment = st.form_submit_button("カードを登録して支払う")

        if submit_payment:
            if not (card_no and holder and expire and cvc):
                st.error("全ての項目を入力してください。")
            else:
                if not FINCODE_API_KEY:
                    st.error("システムエラー: 決済APIキーが設定されていません。")
                    st.stop()
                    
                with st.spinner("決済処理中..."):
                    # 1. DBからFincodeIDを確認
                    users_df = get_users_df(client)
                    user_row = users_df[users_df['ユーザーID'] == str(current_user_id)].iloc[0]
                    
                    # カラムが存在しない場合のエラー回避
                    f_cust_id = ""
                    if 'fincode_customer_id' in users_df.columns:
                        f_cust_id = str(user_row.get('fincode_customer_id', ''))
                    
                    # 2. 顧客IDがない場合、Fincodeに新規作成
                    if not f_cust_id or f_cust_id == "nan" or f_cust_id == "None" or f_cust_id == "":
                        res_cust = fincode_register_customer(current_user_id)
                        if "errors" in res_cust:
                            st.error(f"顧客登録エラー: {res_cust['errors'][0]['error_message']}")
                            st.stop()
                        
                        f_cust_id = res_cust.get("id")
                        if not f_cust_id:
                            st.error("顧客IDの取得に失敗しました。")
                            st.stop()
                            
                        # スプレッドシートにIDを保存
                        if update_user_fincode_id(client, current_user_id, f_cust_id):
                            st.info("顧客情報を新規作成しました。")
                        else:
                            st.error("データベースへのID保存に失敗しました。")
                            st.stop()
                    
                    # 3. カード登録
                    res_card = fincode_register_card(f_cust_id, card_no, expire, cvc, holder)
                    if "errors" in res_card:
                        st.error(f"カード登録エラー: {res_card['errors'][0]['error_message']}")
                    else:
                        # 4. 決済実行
                        success, msg = fincode_execute_payment(f_cust_id, amount)
                        if success:
                            st.success("🎉 支払いが完了しました！")
                            st.balloons()
                            # 成功ログなどを残す場合はここに記述
                        else:
                            st.error(f"決済エラー: {msg}")

if __name__ == "__main__":
    main()
