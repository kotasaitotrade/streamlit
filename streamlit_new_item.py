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

OPTION_PRICE = 2000
PLANS = {
    "full": {
        "name": "フルプラン (全て)", "desc": "アパレル・その他の全てのカテゴリを選択可能", "type": "all",
        "base_price": 9000, "base_id": "price_1T0D0LRp7tXAl48PFa7JBztW", "opt_id": "price_1T0D1yRp7tXAl48P0ep6L76Y"
    },
    "light": {
        "name": "ライトプラン (片方のみ)", "desc": "「アパレル」または「それ以外」のどちらか一方のみ選択可能", "type": "select",
        "base_price": 5000, "base_id": "price_1T0CetRp7tXAl48PCcvLKVJ6", "opt_id": "price_1T0CjERp7tXAl48PLckXXhG4"
    }
}
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

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
        "name": f"通知-{user_name}", "type": 0,
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
#   ユーザー管理・DB操作
# ==========================================
def hash_password(password): return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

@st.cache_data(ttl=60)
def get_users_df(_client):
    try:
        sheet = _client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        data = sheet.get_all_values()
        cols = ['ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'stripe_customer_id', 'subscription_id', 'plan_id', 'チャンネルURL', 'plan', 'valid_until', 'assigned_machine', 'secret_key', 'failed_count', 'locked_until', 'temp_plan_settings']
        if len(data) < 2: return pd.DataFrame(columns=cols)
        df = pd.DataFrame(data[1:], columns=data[0]).astype(str)
        for c in cols:
            if c not in df.columns: df[c] = ""
        return df
    except: return pd.DataFrame()

def login_user(client, login_input, password):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        cell = ws.find(str(login_input))
        if not cell: return False, "ユーザーIDまたはパスワードが間違っています", "", "", ""
        row_values = ws.row_values(cell.row)
        if len(row_values) < 14: row_values += [""] * (14 - len(row_values))
        if row_values[2] == hash_password(password): return True, "成功", row_values[0], row_values[1], row_values[10]
        return False, "ユーザーIDまたはパスワードが間違っています", "", "", ""
    except: return False, "ログイン処理エラー", "", "", ""

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
        sheet.append_row([str(user_id), str(user_name), hash_password(password), "", "", "", webhook_url, "", "", assigned_machine, "", "0", "", ""])
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
            parts = str(row.iloc[0].get('temp_plan_settings', 'all,plan_9000')).split(',')
            if len(parts) >= 2: return parts[0], parts[1]
        return 'all', 'plan_9000'
    except: return 'all', 'plan_9000'

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

# ★ UI用: カンマ区切りのDB文字列を行×列のデータフレームに展開
def expand_keywords_to_dataframe(user_df):
    max_cols = st.session_state.get('kw_col_count', 3)
    expanded_rows = []
    
    for _, row in user_df.iterrows():
        combo = str(row.get('検索条件', '')).strip()
        kw_str = str(row.get('キーワード', '')).strip()
        
        if not kw_str or kw_str.lower() in ['none', 'nan', '(データなし)']:
            expanded_rows.append({'検索条件': combo})
            continue
            
        or_groups = [g.strip() for g in kw_str.replace('、', ',').split(',')]
        for group in or_groups:
            if not group: continue
            and_items = [item.strip() for item in group.replace('　', ' ').split(' ') if item.strip()]
            
            if len(and_items) > max_cols: max_cols = len(and_items)
                
            new_row = {'検索条件': combo}
            for i in range(len(and_items)):
                new_row[f'キーワード{i+1}'] = and_items[i]
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

# ★ 保存用: UIの行×列DFをカンマとスペース区切りのDB文字列に圧縮して保存
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
                
            and_items = []
            for i in range(st.session_state['kw_col_count']):
                val = str(row.get(f'キーワード{i+1}', '')).strip()
                if val and val.lower() not in ["none", "nan"]:
                    # DBフォーマット崩れ防止のため、単語内のスペースとカンマを除去
                    clean_val = val.replace(' ', '').replace('　', '').replace(',', '').replace('、', '')
                    if clean_val: and_items.append(clean_val)
            
            if and_items:
                and_str = ' '.join(and_items)
                if combo not in result_dict: result_dict[combo] = []
                if and_str not in result_dict[combo]: result_dict[combo].append(and_str)
            else:
                if combo not in result_dict: result_dict[combo] = []
                
        new_rows = []
        for combo, and_lists in result_dict.items():
            if len(and_lists) > 30:
                st.error(f"エラー: 「{combo}」の行数が多すぎます（最大30行まで）")
                return None
            kw_str = ', '.join(and_lists)
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
            target_uid = session.metadata.get('user_id')
            if target_uid:
                saved_restriction, saved_plan_id = get_user_temp_settings(client, target_uid)
                update_user_stripe_data(client, target_uid, stripe_id=session.customer, subscription_id=session.subscription, plan_id=saved_plan_id, restriction_type=saved_restriction, valid_until="")
                st.success("🎉 お支払いが完了しました！"); time.sleep(3); st.query_params.clear()
                st.session_state['logged_in_user_id'] = target_uid
                st.rerun()
        st.stop()

    if 'logged_in_user_id' not in st.session_state: st.session_state['logged_in_user_id'] = None

    if st.session_state['logged_in_user_id'] is None:
        st.markdown("## 📊 ツウチマネージャー (市場リサーチツール)")
        tab1, tab2 = st.tabs(["🔑 ログイン", "✨ 新規登録"])
        with tab1:
            li = st.text_input("ID / 名前", key="li")
            lp = st.text_input("パスワード", type="password", key="lp")
            if st.button("ログイン", type="primary"):
                suc, msg, uid, uname, _ = login_user(client, li, lp)
                if suc: st.session_state['logged_in_user_id'] = uid; st.session_state['logged_in_user_name'] = uname; st.rerun()
                else: st.error(msg)
        with tab2:
            ri, rn, rp = st.text_input("Discord ID", key="ri"), st.text_input("表示名", key="rn"), st.text_input("パスワード", type="password", key="rp")
            if st.button("登録"):
                if not ri or not rn or not rp: st.error("入力不足")
                else:
                    suc, msg = register_user(client, ri, rn, rp)
                    if suc: st.success(msg); st.balloons()
                    else: st.error(msg)
        show_tokushoho()
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
    has_option = (current_plan_id in [PLANS["full"]["opt_id"], PLANS["light"]["opt_id"]])

    with st.sidebar:
        st.write(f"User: **{st.session_state.get('logged_in_user_name','')}**")
        menu = st.radio("メニュー", ["通知設定", "プラン契約・解約", "アカウント設定"])
        if st.button("ログアウト"): st.session_state['logged_in_user_id'] = None; st.rerun()

    full_df = load_data(client)

    if menu == "通知設定":
        st.subheader("📢 通知条件の設定")
        if not is_access_allowed: st.error("プラン契約が必要です"); st.stop()

        user_df = full_df[full_df['ユーザーID'] == str(uid)].copy() if full_df is not None else pd.DataFrame()
        
        # UIの列数を管理
        if 'kw_col_count' not in st.session_state:
            st.session_state['kw_col_count'] = 3
            
        display_df = expand_keywords_to_dataframe(user_df)

        if has_option:
            st.success("✅ **キーワード通知オプション: 有効**")
            st.info("""
            💡 **キーワード設定のコツ**
            * **同じ行**の枠に単語を入れると **「かつ (AND)」** になります。（例：キーワード1「ナイキ」, キーワード2「黒」）
            * 表の **行を追加** して同じ条件を選ぶと **「または (OR)」** になります。
            """)
            if st.button("➕ キーワード枠の列を追加する"):
                st.session_state['kw_col_count'] += 1
                st.rerun()
        else:
            st.warning("🔒 **キーワード通知オプション: 無効**")

        column_config = {"検索条件": st.column_config.SelectboxColumn("検索条件", options=get_allowed_options(client, restriction_type))}
        for i in range(st.session_state['kw_col_count']):
            column_config[f"キーワード{i+1}"] = st.column_config.TextColumn(f"キーワード{i+1}", disabled=(not has_option))

        edited = st.data_editor(display_df, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=column_config)
        
        if st.button("設定を保存", type="primary"):
            save_merged_data(client, full_df, edited, uid, restriction_type)

    elif menu == "プラン契約・解約":
        st.subheader("💳 サブスクリプション管理")
        if has_active_sub:
            st.success("✅ **現在プラン契約中です**")
            if st.button("プランを解約する"):
                suc, msg = cancel_stripe_subscription_at_period_end(sub_id)
                if suc: update_user_stripe_data(client, uid, subscription_id="", valid_until=datetime.now().strftime('%Y/%m/%d') if msg == "ALREADY_CANCELED" else msg); st.rerun()
        else:
            plan_key = st.radio("プラン選択", ["full", "light"], format_func=lambda x: f"{PLANS[x]['name']} - ¥{PLANS[x]['base_price']:,}/月")
            use_option = st.checkbox(f"✨ キーワード通知オプションを追加 (+¥{OPTION_PRICE:,})")
            target_plan_id = PLANS[plan_key]['opt_id'] if use_option else PLANS[plan_key]['base_id']
            if st.button("お支払い画面へ進む"):
                suc, url = create_stripe_checkout_session(uid, target_plan_id)
                if suc: st.link_button("支払いを完了させる", url, type="primary")

    elif menu == "アカウント設定":
        st.subheader("⚙️ アカウント設定")
        st.info("機能は一時的に省略されています。")

if __name__ == "__main__":
    main()
