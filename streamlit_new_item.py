import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import json
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- 設定 ---
CREDENTIALS_PATH = 'google_credentials.json' 
TOKEN_PATH = 'gspread_token.json'

SPREADSHEET_ID = "1Y8VEVn95FOp5ELLtBiuUrB9m4S3qDSiX50G6aB88vnk"
TARGET_SHEET_NAME = "ユーザー設定"
USERS_SHEET_NAME = "ユーザー管理"

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

# --- ユーザー管理 ---
def hash_password(password):
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def ensure_users_sheet(client):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            sh.worksheet(USERS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=USERS_SHEET_NAME, rows=100, cols=3)
            ws.append_row(['ユーザーID', 'ユーザー名', 'パスワードハッシュ']) 
    except Exception as e:
        st.error(f"ユーザーDB初期化エラー: {e}")

def get_users_df(client):
    ensure_users_sheet(client)
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        data = sheet.get_all_values()
        if len(data) < 2:
            return pd.DataFrame(columns=['ユーザーID', 'ユーザー名', 'パスワードハッシュ'])
        return pd.DataFrame(data[1:], columns=data[0]).astype(str)
    except Exception as e:
        st.error(f"ユーザー情報取得エラー: {e}")
        return pd.DataFrame(columns=['ユーザーID', 'ユーザー名', 'パスワードハッシュ'])

def register_user(client, user_id, user_name, password):
    users_df = get_users_df(client)
    if str(user_id) in users_df['ユーザーID'].values:
        return False, "このユーザーIDは既に登録されています。"
    if str(user_name) in users_df['ユーザー名'].values:
        return False, "このユーザー名は既に使用されています。"
    
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        hashed_pw = hash_password(password)
        sheet.append_row([str(user_id), str(user_name), hashed_pw])
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

# --- データ読み込み ---
def load_data(client):
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        data = sheet.get_all_values()
        expected_cols = ['ユーザーID', 'サイト', 'カテゴリ', 'ブランドキーワード']

        if not data:
            return pd.DataFrame(columns=expected_cols)
        
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers).astype(str)
        
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return None

# --- データ保存処理 (強化版) ---
def save_merged_data(client, full_df, edited_display_df, user_id):
    try:
        new_rows = []
        error_rows = False
        
        # 編集データの解析
        for i, row in edited_display_df.iterrows():
            combo = row['検索条件']
            keywords = row['ブランドキーワード']
            
            # コンボボックスが空、または正しい形式でない場合はスキップせずに警告フラグを立てる
            if not combo or not isinstance(combo, str) or " - " not in combo:
                # 行自体が完全に空なら無視してOKだが、中途半端に入力されている場合はユーザーに知らせる
                if combo or keywords: 
                    st.warning(f"⚠️ 行 No.{i+1}: サイトとカテゴリの選択が無効です。保存されません。")
                    error_rows = True
                continue

            parts = combo.split(" - ", 1)
            site = parts[0]
            category = parts[1]
            
            new_rows.append({
                'ユーザーID': str(user_id),
                'サイト': site,
                'カテゴリ': category,
                'ブランドキーワード': keywords
            })

        if error_rows:
            st.error("入力内容に不備があるため、一部の行が処理されませんでした。修正して再度保存してください。")
            return None
        
        if new_rows:
            save_user_df = pd.DataFrame(new_rows)
        else:
            save_user_df = pd.DataFrame(columns=['ユーザーID', 'サイト', 'カテゴリ', 'ブランドキーワード'])

        # 他のユーザーデータを保持
        other_users_df = full_df[full_df['ユーザーID'] != str(user_id)]
        
        cols = ['ユーザーID', 'サイト', 'カテゴリ', 'ブランドキーワード']
        for c in cols:
            if c not in save_user_df.columns: save_user_df[c] = ""
            if c not in other_users_df.columns: other_users_df[c] = ""
            
        save_user_df = save_user_df.reindex(columns=cols)
        other_users_df = other_users_df.reindex(columns=cols)
        
        final_df = pd.concat([other_users_df, save_user_df], ignore_index=True)
        
        # --- 書き込み実行 ---
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(TARGET_SHEET_NAME)
        update_data = [final_df.columns.tolist()] + final_df.astype(str).values.tolist()
        
        sheet.clear()
        
        # gspreadのバージョン互換性対応
        try:
            # 新しいバージョン (v6.0.0以降)
            sheet.update(values=update_data, range_name='A1')
        except TypeError:
            # 古いバージョン
            sheet.update('A1', update_data)
        
        # 自分のデータ件数をカウント
        my_count = len(save_user_df)
        st.success(f"✅ 設定を保存しました！（あなたの設定: {my_count}件）")
        return final_df

    except Exception as e:
        st.error(f"保存中にエラーが発生しました。\n詳細: {e}")
        # 権限エラーの可能性を示唆
        if "403" in str(e) or "PERMISSION_DENIED" in str(e):
            st.error("⚠️ ヒント: 認証に使用したGoogleアカウントに、このスプレッドシートの「編集権限」が付与されていない可能性があります。スプレッドシートの「共有」設定を確認してください。")
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
            st.info("DiscordのユーザーIDと、表示用のユーザー名を設定してください。")
            r_id = st.text_input("DiscordユーザーID (必須)", key="reg_id")
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
        st.caption(f"ID: {current_user_id}")
        if st.button("ログアウト"):
            st.session_state['logged_in_user_id'] = None
            st.session_state['logged_in_user_name'] = None
            st.rerun()

    full_df = load_data(client)
    if full_df is None:
        return

    # 選択肢生成
    if not full_df.empty:
        valid_pairs_df = full_df[['サイト', 'カテゴリ']].drop_duplicates()
        valid_pairs_df = valid_pairs_df[
            (valid_pairs_df['サイト'] != '') & 
            (valid_pairs_df['カテゴリ'] != '') & 
            (valid_pairs_df['サイト'].notna()) & 
            (valid_pairs_df['カテゴリ'].notna())
        ]
        valid_options = sorted([f"{row['サイト']} - {row['カテゴリ']}" for _, row in valid_pairs_df.iterrows()])
    else:
        valid_options = []

    user_df = full_df[full_df['ユーザーID'] == str(current_user_id)].copy()

    if not user_df.empty:
        user_df['検索条件'] = user_df.apply(lambda x: f"{x['サイト']} - {x['カテゴリ']}", axis=1)
    else:
        user_df['検索条件'] = []

    display_df = user_df[['検索条件', 'ブランドキーワード']].copy()
    display_df.index = range(1, len(display_df) + 1)

    st.markdown(f"### {current_user_name} さんの通知設定")

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
            # 重複・不備チェック
            valid_entries = edited_display_df[edited_display_df['検索条件'].notna() & (edited_display_df['検索条件'] != "")]
            if valid_entries['検索条件'].duplicated().any():
                duplicates = valid_entries[valid_entries['検索条件'].duplicated()]['検索条件'].unique()
                st.error(f"⚠️ エラー: 以下のカテゴリが重複しています。\n\n" + ", ".join(duplicates))
            else:
                new_full_df = save_merged_data(client, full_df, edited_display_df, current_user_id)
                if new_full_df is not None:
                    st.session_state.df = new_full_df
                    st.rerun()

    with col2:
        if st.button("🔄 最新データを再読み込み"):
            st.rerun()

if __name__ == "__main__":
    main()
