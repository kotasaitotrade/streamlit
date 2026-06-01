"""
管理者・営業者専用アプリ
- 管理者 (role=admin): ユーザー管理 / 月額料金参照 / パスワード管理 / 営業者アカウント管理
- 営業者 (role=sales): 月額料金参照のみ
"""
import streamlit as st
import pandas as pd
import gspread
import os
import hashlib
import json
import time
import stripe
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError

st.set_page_config(page_title="管理者パネル", layout="wide")

# ==========================================
#   設定・定数（streamlit_new_item.py と共通）
# ==========================================
CREDENTIALS_PATH = 'google_credentials.json'
TOKEN_PATH = 'gspread_token.json'
SPREADSHEET_ID = "1Y8VEVn95FOp5ELLtBiuUrB9m4S3qDSiX50G6aB88vnk"
USERS_SHEET_NAME = "ユーザー管理"
MACHINES = ["machine_1", "machine_2"]

PLANS = {
    "full": {
        "name": "フルプラン (全て)",
        "base_id": "price_1TZw2rRuq87ZH1shVVdNkhXn", "opt_id": "price_1TZw26Ruq87ZH1shxQJwa4OA",
        "base_plan_id": "plan_9000", "opt_plan_id": "plan_11000"
    },
    "light": {
        "name": "ライトプラン (片方のみ)",
        "base_id": "price_1TZw5qRuq87ZH1shCHiJxTif", "opt_id": "price_1TZw3tRuq87ZH1shTbNIco8T",
        "base_plan_id": "plan_5000", "opt_plan_id": "plan_7000"
    }
}

SALES_COMMISSION = {
    "plan_9000": 4500, "plan_11000": 4500,
    "plan_5000": 2500, "plan_7000": 2500,
}
PLAN_DISPLAY_PRICE = {
    "plan_9000": 9000, "plan_11000": 11000,
    "plan_5000": 5000, "plan_7000": 7000,
}
PLAN_DISPLAY_NAME = {
    "plan_9000": "フル ¥9,000", "plan_11000": "フル+OPT ¥11,000",
    "plan_5000": "ライト ¥5,000", "plan_7000": "ライト+OPT ¥7,000",
}

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

USER_COLS = [
    'ユーザーID', 'ユーザー名', 'パスワードハッシュ', 'stripe_customer_id', 'subscription_id',
    'plan_id', 'チャンネルURL', 'plan', 'valid_until', 'assigned_machine', 'secret_key',
    'failed_count', 'locked_until', 'temp_plan_settings', 'role', 'joined_at',
    'assigned_sales', 'force_pw_change', 'paid_months'
]

# ==========================================
#   Secrets & 認証
# ==========================================
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
    except:
        pass

create_json_from_secrets()

try:
    stripe.api_key = st.secrets["stripe"]["api_key"]
except:
    stripe.api_key = ""

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

# ==========================================
#   DB操作
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

def _find_user_row_num(ws, user_id):
    try:
        col_values = ws.col_values(1)
        for i, val in enumerate(col_values):
            if val == str(user_id):
                return i + 1
        return None
    except:
        return None

def update_user_field(client, user_id, col_name, value):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        headers = ws.row_values(1)
        col_idx = headers.index(col_name) + 1 if col_name in headers else USER_COLS.index(col_name) + 1
        row_num = _find_user_row_num(ws, user_id)
        if row_num:
            ws.update_cell(row_num, col_idx, str(value))
            get_users_df.clear()
            return True, "更新しました"
        return False, "ユーザーが見つかりません"
    except Exception as e:
        return False, str(e)

def ensure_user_sheet_headers(client):
    if st.session_state.get('_headers_ensured'):
        return
    st.session_state['_headers_ensured'] = True
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        headers = ws.row_values(1)
        new_headers = [c for c in USER_COLS if c not in headers]
        if not new_headers:
            return
        base = max(len(headers), ws.col_count)
        needed_cols = base + len(new_headers)
        try:
            ws.resize(rows=ws.row_count, cols=needed_cols)
        except Exception:
            pass
        for i, h in enumerate(new_headers):
            try:
                ws.update_cell(1, base + 1 + i, h)
            except Exception:
                pass
        get_users_df.clear()
    except Exception:
        pass

def login_admin(client, login_input, password):
    """管理者・営業者のログイン"""
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        row_num = _find_user_row_num(ws, login_input)
        if not row_num:
            name_col = ws.col_values(2)
            for i, val in enumerate(name_col):
                if val == str(login_input):
                    row_num = i + 1
                    break
        if not row_num:
            return False, "IDまたはパスワードが違います", "", "", "", ""
        row_values = ws.row_values(row_num)
        while len(row_values) < len(USER_COLS):
            row_values.append("")
        if row_values[2] != hash_password(password):
            return False, "IDまたはパスワードが違います", "", "", "", ""
        headers = ws.row_values(1)
        role_idx = headers.index('role') if 'role' in headers else 14
        role = (row_values[role_idx] if role_idx < len(row_values) else "") or \
               (row_values[14] if 14 < len(row_values) else "") or "user"
        if role not in ['admin', 'sales']:
            return False, "このアカウントには管理者パネルへのアクセス権がありません", "", "", "", ""
        force_pw_idx = headers.index('force_pw_change') if 'force_pw_change' in headers else 17
        force_pw = (row_values[force_pw_idx] if force_pw_idx < len(row_values) else "") or \
                   (row_values[17] if 17 < len(row_values) else "")
        return True, "成功", row_values[0], row_values[1], role, force_pw
    except:
        return False, "ログイン処理エラー", "", "", "", ""

# ==========================================
#   Stripe
# ==========================================
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
    except Exception as e:
        return False, str(e)

# ==========================================
#   管理者用ロジック
# ==========================================
def admin_disable_user(client, user_id, subscription_id):
    if subscription_id and subscription_id not in ["", "nan", "None"]:
        suc, end_date = cancel_stripe_subscription_at_period_end(subscription_id)
        if suc and end_date not in ["ALREADY_CANCELED", ""]:
            update_user_field(client, user_id, 'valid_until', end_date)
    return update_user_field(client, user_id, 'role', 'disabled')

def admin_force_change_plan(client, user_id, subscription_id, new_plan_key, use_option, restriction_override=None):
    try:
        plan = PLANS[new_plan_key]
        new_price_id = plan['opt_id'] if use_option else plan['base_id']
        new_plan_id = plan['opt_plan_id'] if use_option else plan['base_plan_id']
        new_restriction = restriction_override if restriction_override else ("all" if new_plan_key == "full" else "apparel")
        if subscription_id and subscription_id not in ["", "nan", "None"]:
            ok, msg = change_stripe_subscription_plan(subscription_id, new_price_id)
            if not ok: return False, msg
        update_user_field(client, user_id, 'plan_id', new_plan_id)
        update_user_field(client, user_id, 'plan', new_restriction)
        get_users_df.clear()
        return True, f"プランを変更しました: {PLAN_DISPLAY_NAME.get(new_plan_id, new_plan_id)}"
    except Exception as e:
        return False, str(e)

def create_sales_account(client, user_id, user_name, password):
    get_users_df.clear()
    users_df = get_users_df(client)
    if str(user_id) in users_df['ユーザーID'].values: return False, "ID重複"
    if str(user_name) in users_df['ユーザー名'].values: return False, "名前重複"
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(USERS_SHEET_NAME)
        sheet.append_row([
            str(user_id), str(user_name), hash_password(password), "", "", "",
            "", "", "", "", "", "0", "", "",
            "sales", "", "", ""
        ])
        get_users_df.clear()
        return True, "営業者アカウントを作成しました"
    except Exception as e:
        return False, f"エラー: {e}"

def get_monthly_fee_data(users_df, year, month):
    first_day = datetime(year, month, 1).date()
    last_day = datetime(year, month, monthrange(year, month)[1]).date()
    result = []
    for _, row in users_df.iterrows():
        role = str(row.get('role', 'user')).strip()
        if role in ['admin', 'sales']:
            continue
        joined_str = str(row.get('joined_at', '')).strip()
        plan_id = str(row.get('plan_id', '')).strip()
        if not joined_str or joined_str in ['', 'nan', 'None']: continue
        if not plan_id or plan_id in ['', 'nan', 'None']: continue
        try:
            joined_date = datetime.strptime(joined_str.split(' ')[0], '%Y/%m/%d').date()
        except:
            continue
        if joined_date > last_day:
            continue
        left_str = str(row.get('valid_until', '')).strip()
        left_date = None
        left_display = "継続中"
        if left_str and left_str not in ['nan', 'None', '']:
            try:
                left_date = datetime.strptime(left_str.split(' ')[0], '%Y/%m/%d').date()
                if left_date < first_day:
                    continue
                left_display = left_str.split(' ')[0]
            except:
                pass
        status = "退会済" if (left_date and left_date <= last_day) else "継続中"
        result.append({
            'ユーザーID': str(row.get('ユーザーID', '')),
            'ユーザー名': str(row.get('ユーザー名', '')),
            'プラン名': PLAN_DISPLAY_NAME.get(plan_id, plan_id),
            '月額料金': PLAN_DISPLAY_PRICE.get(plan_id, 0),
            '営業者取り分': SALES_COMMISSION.get(plan_id, 0),
            '入会日': joined_str.split(' ')[0],
            '退会日': left_display,
            'ステータス': status,
            '担当営業者ID': str(row.get('assigned_sales', '')),
        })
    return pd.DataFrame(result) if result else pd.DataFrame(columns=[
        'ユーザーID', 'ユーザー名', 'プラン名', '月額料金', '営業者取り分',
        '入会日', '退会日', 'ステータス', '担当営業者ID'
    ])

# ==========================================
#   ページ: ユーザー管理
# ==========================================
def show_user_management(client, users_df):
    st.subheader("👥 ユーザー管理")

    # 最後の操作結果を表示（rerun後も見える）
    if st.session_state.get('_last_op_result'):
        ok, msg = st.session_state.pop('_last_op_result')
        if ok: st.success(msg)
        else: st.error(msg)

    tab_users, tab_sales = st.tabs(["ユーザー一覧", "営業者管理"])

    with tab_users:
        target_df = users_df[~users_df['role'].isin(['admin'])].copy()
        sales_df = users_df[users_df['role'] == 'sales'][['ユーザーID', 'ユーザー名']]
        sales_map = {str(r['ユーザーID']): str(r['ユーザー名']) for _, r in sales_df.iterrows()}

        if target_df.empty:
            st.info("ユーザーがいません")
            return

        search = st.text_input("ユーザー名 / IDで検索", key="user_search")
        if search:
            mask = (target_df['ユーザー名'].str.contains(search, na=False) |
                    target_df['ユーザーID'].str.contains(search, na=False))
            target_df = target_df[mask]

        for _, user in target_df.iterrows():
            uid = str(user['ユーザーID'])
            uname = str(user['ユーザー名'])
            role = str(user.get('role', 'user'))
            sub_id = str(user.get('subscription_id', ''))
            machine = str(user.get('assigned_machine', ''))
            plan_id = str(user.get('plan_id', ''))
            plan_type = str(user.get('plan', ''))
            assigned_sales_id = str(user.get('assigned_sales', ''))
            joined_at = str(user.get('joined_at', '-'))
            valid_until = str(user.get('valid_until', '-'))

            role_badge = {"sales": "🟡 営業者", "disabled": "⚫ 無効", "user": "🟢 ユーザー"}.get(role, "🟢 ユーザー")

            with st.expander(f"**{uname}** ({uid})　{role_badge}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**マシン:** {machine}")
                    st.write(f"**プラン:** {PLAN_DISPLAY_NAME.get(plan_id, plan_id or '未契約')}")
                    st.write(f"**入会日:** {joined_at}")
                with c2:
                    st.write(f"**サブスクID:** {sub_id[:40] if sub_id not in ['', 'nan', 'None'] else 'なし'}")
                    st.write(f"**有効期限:** {valid_until}")
                    s_name = sales_map.get(assigned_sales_id, "")
                    st.write(f"**担当営業:** {f'{s_name}({assigned_sales_id})' if s_name else '未割当'}")

                if assigned_sales_id and assigned_sales_id in sales_map and role != 'disabled':
                    st.divider()
                    now = datetime.now()
                    commission = SALES_COMMISSION.get(plan_id, 0)
                    due_date = _payment_due_date(joined_at, now.year, now.month)
                    paid_months_str = str(user.get('paid_months', ''))
                    is_paid = _is_paid(paid_months_str, now.year, now.month)

                    pcol1, pcol2, pcol3 = st.columns([2, 2, 2])
                    pcol1.write(f"**営業者支払額:** ¥{commission:,}")
                    pcol2.write(f"**支払予定日:** {due_date.strftime('%Y/%m/%d') if due_date else '-'}")
                    with pcol3:
                        new_paid = st.checkbox(
                            f"{now.month}月分 支払済み",
                            value=is_paid,
                            key=f"paid_{uid}_{now.year}_{now.month}",
                        )
                        if new_paid != is_paid:
                            new_val = _set_paid(paid_months_str, now.year, now.month, new_paid)
                            ok, msg = update_user_field(client, uid, 'paid_months', new_val)
                            if ok:
                                st.session_state['_last_op_result'] = (True, f"{uname} の{now.month}月分支払い状態を更新")
                                st.rerun()
                            else:
                                st.error(f"更新失敗: {msg}")

                st.divider()
                col_a, col_b, col_c, col_d = st.columns(4)

                with col_a:
                    st.write("**アカウント状態**")
                    # ロール変更（user ↔ sales）
                    role_opts = ["user", "sales"]
                    role_labels = {"user": "🟢 ユーザー", "sales": "🟡 営業者"}
                    cur_role_idx = role_opts.index(role) if role in role_opts else 0
                    new_role = st.selectbox(
                        "ロール", role_opts,
                        format_func=lambda x: role_labels[x],
                        index=cur_role_idx,
                        key=f"role_{uid}",
                        label_visibility="collapsed"
                    )
                    if st.button("ロール変更", key=f"role_btn_{uid}"):
                        ok, msg = update_user_field(client, uid, 'role', new_role)
                        get_users_df.clear()
                        if ok:
                            st.session_state['_last_op_result'] = (True, f"{role_labels[new_role]} に変更しました")
                        else:
                            st.session_state['_last_op_result'] = (False, f"ロール変更失敗: {msg}")
                        st.rerun()
                    # 無効化 / 有効化
                    if role == 'disabled':
                        if st.button("✅ 有効化", key=f"enable_{uid}"):
                            ok, msg = update_user_field(client, uid, 'role', 'user')
                            if ok: st.success("有効化しました"); st.rerun()
                            else: st.error(msg)
                    else:
                        if st.button("🚫 強制無効化", key=f"disable_{uid}"):
                            ok, msg = admin_disable_user(client, uid, sub_id)
                            if ok: st.success("無効化しました（Stripeは期間末解約）"); st.rerun()
                            else: st.error(msg)

                with col_b:
                    st.write("**マシン変更**")
                    cur_idx = MACHINES.index(machine) if machine in MACHINES else 0
                    new_machine = st.selectbox("マシン", MACHINES, index=cur_idx,
                                               key=f"machine_{uid}", label_visibility="collapsed")
                    if st.button("変更", key=f"machine_btn_{uid}"):
                        ok, msg = update_user_field(client, uid, 'assigned_machine', new_machine)
                        if ok: st.success(f"{new_machine} に変更"); st.rerun()
                        else: st.error(msg)

                with col_c:
                    st.write("**プラン変更**")
                    plan_keys = list(PLANS.keys())
                    cur_pk = "full"
                    for k, v in PLANS.items():
                        if plan_id in [v['base_plan_id'], v['opt_plan_id']]:
                            cur_pk = k; break
                    new_pk = st.selectbox("プラン", plan_keys, format_func=lambda x: PLANS[x]['name'],
                                          index=plan_keys.index(cur_pk), key=f"plan_{uid}", label_visibility="collapsed")
                    use_opt = st.checkbox("OPT付き", key=f"opt_{uid}",
                                          value=(plan_id in ["plan_11000", "plan_7000"]))
                    if new_pk == "light":
                        ro_opts = ["apparel", "not_apparel"]
                        ro_labels = {"apparel": "アパレル", "not_apparel": "その他"}
                        cur_ro = plan_type if plan_type in ro_opts else "apparel"
                        new_ro = st.selectbox("カテゴリ", ro_opts, format_func=lambda x: ro_labels[x],
                                              index=ro_opts.index(cur_ro), key=f"ro_{uid}", label_visibility="collapsed")
                    else:
                        new_ro = "all"
                    if st.button("プラン変更", key=f"plan_btn_{uid}"):
                        ok, msg = admin_force_change_plan(client, uid, sub_id, new_pk, use_opt, new_ro)
                        if ok: st.success(msg); st.rerun()
                        else: st.error(msg)

                with col_d:
                    st.write("**担当営業者**")
                    s_ids = [""] + list(sales_map.keys())
                    s_labels = ["(なし)"] + [f"{v}({k})" for k, v in sales_map.items()]
                    cur_si = s_ids.index(assigned_sales_id) if assigned_sales_id in s_ids else 0
                    new_sid = st.selectbox("営業者", s_ids,
                                           format_func=lambda x: s_labels[s_ids.index(x)] if x in s_ids else x,
                                           index=cur_si, key=f"sales_{uid}", label_visibility="collapsed")
                    if st.button("割り当て", key=f"sales_btn_{uid}"):
                        ok, msg = update_user_field(client, uid, 'assigned_sales', new_sid)
                        if ok: st.success("担当営業者を割り当てました"); st.rerun()
                        else: st.error(msg)

    with tab_sales:
        now = datetime.now()
        st.write(f"#### 営業者一覧（{now.year}年{now.month}月 支払い状況）")
        sales_list = users_df[users_df['role'] == 'sales'].copy()
        if sales_list.empty:
            st.info("営業者アカウントはまだありません")
        else:
            sales_rows = []
            for _, s in sales_list.iterrows():
                sid = str(s['ユーザーID'])
                sname = str(s['ユーザー名'])
                # 担当ユーザー（無効を除く）
                assigned = users_df[
                    (users_df['assigned_sales'] == sid) &
                    (~users_df['role'].isin(['admin', 'sales', 'disabled']))
                ]
                paid_amt = 0
                pending_amt = 0
                for _, u in assigned.iterrows():
                    plan_id = str(u.get('plan_id', ''))
                    commission = SALES_COMMISSION.get(plan_id, 0)
                    valid_until = str(u.get('valid_until', '')).strip()
                    if valid_until and valid_until not in ['', 'nan', 'None'] and _is_expired(valid_until):
                        continue
                    if _is_paid(str(u.get('paid_months', '')), now.year, now.month):
                        paid_amt += commission
                    else:
                        pending_amt += commission
                total = paid_amt + pending_amt
                sales_rows.append({
                    'ID': sid,
                    '名前': sname,
                    '担当ユーザー数': f"{len(assigned)}人",
                    '今月合計': f"¥{total:,}",
                    '支払済': f"¥{paid_amt:,}",
                    '未払い': f"¥{pending_amt:,}",
                })
            sales_df_disp = pd.DataFrame(sales_rows)

            def hl_pending(row):
                if row.get('未払い') and row['未払い'] != '¥0':
                    return ['background-color: #fff3cd'] * len(row)
                return [''] * len(row)

            st.dataframe(sales_df_disp.style.apply(hl_pending, axis=1),
                         use_container_width=True, hide_index=True)
        st.divider()
        st.write("#### 営業者アカウント作成")
        with st.form("create_sales_form"):
            s_id = st.text_input("ログインID（任意の文字列）")
            s_name = st.text_input("表示名")
            s_pw = st.text_input("初期パスワード", type="password")
            s_force = st.checkbox("初回ログイン時にパスワード変更を要求する", value=True)
            if st.form_submit_button("作成", type="primary"):
                if not s_id or not s_name or not s_pw:
                    st.error("全項目を入力してください")
                else:
                    ok, msg = create_sales_account(client, s_id, s_name, s_pw)
                    if ok:
                        if s_force:
                            update_user_field(client, s_id, 'force_pw_change', "1")
                        st.success(msg); st.rerun()
                    else:
                        st.error(msg)

# ==========================================
#   ページ: 月額料金参照
# ==========================================
def show_monthly_fee(client, users_df, current_uid, current_role):
    st.subheader("💰 月額料金参照")
    now = datetime.now()
    c1, c2 = st.columns(2)
    with c1: year = st.number_input("年", min_value=2024, max_value=now.year + 1, value=now.year, step=1)
    with c2: month = st.number_input("月", min_value=1, max_value=12, value=now.month, step=1)

    fee_df = get_monthly_fee_data(users_df, int(year), int(month))
    if current_role == 'sales':
        fee_df = fee_df[fee_df['担当営業者ID'] == str(current_uid)].copy()

    if fee_df.empty:
        st.info(f"{int(year)}年{int(month)}月のデータはありません"); return

    sales_map = {str(r['ユーザーID']): str(r['ユーザー名'])
                 for _, r in users_df[users_df['role'] == 'sales'].iterrows()}

    if current_role == 'admin':
        fee_df['担当営業者名'] = fee_df['担当営業者ID'].map(
            lambda x: sales_map.get(x, '未割当' if not x or x == 'nan' else x))

    display_cols = (['ユーザー名', 'プラン名', '月額料金', '入会日', '退会日', 'ステータス', '担当営業者名', '営業者取り分']
                    if current_role == 'admin' else
                    ['ユーザー名', 'プラン名', '月額料金', '入会日', '退会日', 'ステータス', '営業者取り分'])
    display_df = fee_df[[c for c in display_cols if c in fee_df.columns]].copy()

    def highlight_status(row):
        if row.get('ステータス') == '退会済':
            return ['background-color: #fff3cd'] * len(row)
        return [''] * len(row)

    st.dataframe(display_df.style.apply(highlight_status, axis=1), use_container_width=True, hide_index=True)
    st.divider()

    c1, c2, c3 = st.columns(3)
    c1.metric("対象ユーザー数", f"{len(fee_df)}人")
    c2.metric("月額合計（売上）", f"¥{fee_df['月額料金'].sum():,}")
    label = f"{int(month)}月分 支払い予定" if current_role == 'sales' else "営業者取り分合計"
    c3.metric(label, f"¥{fee_df['営業者取り分'].sum():,}")

    if current_role == 'admin' and '担当営業者名' in fee_df.columns:
        st.divider()
        st.write("#### 営業者別 支払い一覧")
        summary = (fee_df.groupby('担当営業者名')
                   .agg(担当ユーザー数=('ユーザー名', 'count'), 支払い金額=('営業者取り分', 'sum'))
                   .reset_index().sort_values('支払い金額', ascending=False))
        summary['支払い金額'] = summary['支払い金額'].apply(lambda x: f"¥{x:,}")
        st.dataframe(summary, use_container_width=True, hide_index=True)

# ==========================================
#   営業者支払い 共通ヘルパー
# ==========================================
def _payment_due_date(joined_at_str, year, month):
    """毎月の支払日 = 入会日の「日」。年月を指定。"""
    try:
        d = datetime.strptime(joined_at_str.strip().split(' ')[0], '%Y/%m/%d')
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        return datetime(year, month, min(d.day, last_day)).date()
    except:
        return None

def _is_paid(paid_months_str, year, month):
    key = f"{year:04d}-{month:02d}"
    return key in [m.strip() for m in str(paid_months_str).split(',') if m.strip()]

def _set_paid(paid_months_str, year, month, paid):
    key = f"{year:04d}-{month:02d}"
    months = [m.strip() for m in str(paid_months_str).split(',') if m.strip()]
    if paid and key not in months:
        months.append(key)
    elif not paid and key in months:
        months = [m for m in months if m != key]
    return ','.join(sorted(months))


# ==========================================
#   ページ: 担当ユーザー一覧（営業者用）
# ==========================================
def _is_expired(valid_until_str):
    try:
        exp = datetime.strptime(valid_until_str.strip().split(' ')[0], '%Y/%m/%d').date()
        return exp <= datetime.now().date()
    except:
        return False

def _billing_confirmed(joined_at_str):
    try:
        billing_day = datetime.strptime(joined_at_str.strip().split(' ')[0], '%Y/%m/%d').day
        return datetime.now().date().day >= billing_day
    except:
        return False

def show_assigned_users(users_df, current_uid):
    st.subheader("👤 担当ユーザー一覧")

    assigned = users_df[
        (users_df['assigned_sales'] == str(current_uid)) &
        (~users_df['role'].isin(['admin', 'sales']))
    ].copy()

    if assigned.empty:
        st.info("担当ユーザーはまだいません")
        return

    rows = []
    for _, u in assigned.iterrows():
        plan_id = str(u.get('plan_id', ''))
        valid_until = str(u.get('valid_until', '')).strip()
        role = str(u.get('role', 'user'))

        if role == 'disabled':
            status = "⚫ 無効"
        elif valid_until and valid_until not in ['', 'nan', 'None']:
            try:
                exp = datetime.strptime(valid_until.split(' ')[0], '%Y/%m/%d').date()
                status = "退会済" if exp <= datetime.now().date() else "継続中"
            except:
                status = "継続中"
        else:
            status = "継続中"

        joined_at_raw = str(u.get('joined_at', '')).strip()
        today = datetime.now().date()
        now = datetime.now()
        commission = SALES_COMMISSION.get(plan_id, 0)
        due_date = _payment_due_date(joined_at_raw, now.year, now.month)
        paid_months_str = str(u.get('paid_months', ''))
        is_paid = _is_paid(paid_months_str, now.year, now.month)

        if status in ['退会済', '⚫ 無効']:
            commission_str = '-'
            payment_status = '-'
        elif is_paid:
            commission_str = f"¥{commission:,}"
            payment_status = '✅ 支払済'
        elif due_date and today >= due_date:
            commission_str = f"¥{commission:,}"
            payment_status = '⏳ 支払待ち'
        else:
            commission_str = f"¥{commission:,}"
            payment_status = f"📅 {due_date.strftime('%m/%d')}予定" if due_date else '-'

        rows.append({
            'ユーザー名': str(u.get('ユーザー名', '')),
            'ユーザーID': str(u.get('ユーザーID', '')),
            'プラン': PLAN_DISPLAY_NAME.get(plan_id, plan_id or '未契約'),
            '入会日': joined_at_raw.split(' ')[0] if joined_at_raw and joined_at_raw not in ['nan', 'None', ''] else '-',
            '有効期限': valid_until.split(' ')[0] if valid_until and valid_until not in ['nan', 'None', ''] else '継続中',
            'ステータス': status,
            '今月入金額': commission_str,
            '支払状況': payment_status,
        })

    df = pd.DataFrame(rows)
    active_count = len([r for r in rows if r['ステータス'] == '継続中'])
    now = datetime.now()
    paid_total = sum(
        SALES_COMMISSION.get(str(u.get('plan_id', '')), 0)
        for _, u in assigned.iterrows()
        if _is_paid(str(u.get('paid_months', '')), now.year, now.month)
    )
    pending_total = sum(
        SALES_COMMISSION.get(str(u.get('plan_id', '')), 0)
        for _, u in assigned.iterrows()
        if str(u.get('role', '')) != 'disabled'
        and not (str(u.get('valid_until', '')).strip() not in ['', 'nan', 'None'] and
                 _is_expired(str(u.get('valid_until', ''))))
        and not _is_paid(str(u.get('paid_months', '')), now.year, now.month)
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("担当ユーザー数", f"{len(df)}人（継続中 {active_count}人）")
    c2.metric(f"{now.month}月 支払済合計", f"¥{paid_total:,}")
    c3.metric(f"{now.month}月 未払い", f"¥{pending_total:,}")

    def highlight_status(row):
        if row.get('ステータス') in ['退会済', '⚫ 無効']:
            return ['background-color: #fff3cd'] * len(row)
        if row.get('支払状況') == '✅ 支払済':
            return ['background-color: #d4edda'] * len(row)
        return [''] * len(row)

    st.dataframe(df.style.apply(highlight_status, axis=1), use_container_width=True, hide_index=True)


# ==========================================
#   ページ: パスワード管理
# ==========================================
def show_password_management(client, users_df):
    st.subheader("🔑 パスワード管理")
    target_df = users_df[users_df['role'] != 'admin'][['ユーザーID', 'ユーザー名', 'role']].copy()
    if target_df.empty:
        st.info("対象ユーザーがいません"); return

    role_label = {"user": "ユーザー", "sales": "営業者", "disabled": "無効"}
    options = [f"{r['ユーザー名']} ({r['ユーザーID']}) [{role_label.get(r['role'], r['role'])}]"
               for _, r in target_df.iterrows()]
    user_ids = target_df['ユーザーID'].tolist()
    idx = st.selectbox("対象ユーザーを選択", range(len(options)), format_func=lambda i: options[i])
    selected_uid = user_ids[idx]

    with st.form("pw_form"):
        new_pw = st.text_input("新しいパスワード", type="password")
        confirm_pw = st.text_input("確認（再入力）", type="password")
        force_change = st.checkbox("次回ログイン時にパスワード変更を要求する", value=True)
        if st.form_submit_button("変更する", type="primary"):
            if not new_pw or not confirm_pw: st.error("パスワードを入力してください")
            elif new_pw != confirm_pw: st.error("パスワードが一致しません")
            elif len(new_pw) < 6: st.error("パスワードは6文字以上で設定してください")
            else:
                ok, msg = update_user_field(client, selected_uid, 'パスワードハッシュ', hash_password(new_pw))
                if ok:
                    flag = "1" if force_change else ""
                    update_user_field(client, selected_uid, 'force_pw_change', flag)
                    st.success("パスワードを変更しました")
                    if force_change: st.info("次回そのユーザーがログインすると、パスワード変更画面が表示されます。")
                else:
                    st.error(msg)

# ==========================================
#   ページ: 強制パスワード変更
# ==========================================
def show_force_password_change(client, uid):
    st.title("🔐 パスワードの変更が必要です")
    st.warning("管理者によってパスワードの変更が要求されています。新しいパスワードを設定してください。")
    with st.form("force_pw_form"):
        new_pw = st.text_input("新しいパスワード", type="password")
        confirm_pw = st.text_input("確認（再入力）", type="password")
        if st.form_submit_button("パスワードを変更する", type="primary"):
            if not new_pw or not confirm_pw: st.error("パスワードを入力してください")
            elif new_pw != confirm_pw: st.error("パスワードが一致しません")
            elif len(new_pw) < 6: st.error("パスワードは6文字以上で設定してください")
            else:
                update_user_field(client, uid, 'パスワードハッシュ', hash_password(new_pw))
                update_user_field(client, uid, 'force_pw_change', "")
                st.success("パスワードを変更しました")
                st.session_state['force_pw_change'] = False
                time.sleep(1.5)
                st.rerun()

# ==========================================
#   メイン
# ==========================================
def main():
    client = get_gspread_client()
    if not client:
        st.error("データベース接続エラー。管理者に連絡してください。")
        return

    ensure_user_sheet_headers(client)

    # セッション初期化
    for key, default in [('logged_in_uid', None), ('logged_in_name', ''),
                         ('user_role', ''), ('force_pw_change', False)]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 未ログイン
    if not st.session_state['logged_in_uid']:
        st.markdown("## 🔐 管理者パネル")
        login_id = st.text_input("ログインID")
        login_pw = st.text_input("パスワード", type="password")
        if st.button("ログイン", type="primary"):
            suc, msg, uid, uname, role, force_pw = login_admin(client, login_id, login_pw)
            if suc:
                st.session_state['logged_in_uid'] = uid
                st.session_state['logged_in_name'] = uname
                st.session_state['user_role'] = role
                st.session_state['force_pw_change'] = (force_pw == "1")
                st.rerun()
            else:
                st.error(msg)
        st.stop()

    uid = st.session_state['logged_in_uid']
    role = st.session_state['user_role']

    # パスワード強制変更
    if st.session_state.get('force_pw_change'):
        show_force_password_change(client, uid)
        st.stop()

    users_df = get_users_df(client)

    # サイドバー
    with st.sidebar:
        role_badge = {"admin": "🔴 管理者", "sales": "🟡 営業者"}.get(role, role)
        st.write(f"**{st.session_state['logged_in_name']}**")
        st.caption(role_badge)
        st.divider()

        menu_options = ["担当ユーザー", "月額料金参照"]
        if role == 'admin':
            menu_options = ["ユーザー管理", "月額料金参照", "パスワード管理"]

        menu = st.radio("メニュー", menu_options)
        st.divider()
        if st.button("ログアウト"):
            for k in ['logged_in_uid', 'logged_in_name', 'user_role', 'force_pw_change']:
                st.session_state.pop(k, None)
            st.rerun()

    # ルーティング
    if menu == "ユーザー管理" and role == 'admin':
        show_user_management(client, users_df)
    elif menu == "担当ユーザー" and role == 'sales':
        show_assigned_users(users_df, uid)
    elif menu == "月額料金参照":
        show_monthly_fee(client, users_df, uid, role)
    elif menu == "パスワード管理" and role == 'admin':
        show_password_management(client, users_df)


if __name__ == "__main__":
    main()
