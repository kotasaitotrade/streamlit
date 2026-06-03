# せどりツール クロスセル運用メモ

EC新着監視（既存サービス）の利用者に **メルカリ/ヤフフリ用 sedori ツール**
を追加販売するためのリポ内仕掛けと、有効化の手順をまとめます。

## 全体像

```
[既存EC契約者]                    [新規 sedori 契約者]
       │                                  │
       │ streamlit_new_item.py            │
       │ プラン契約・解約 メニューで       │
       │ 「🛒 せどりツールも追加できます」│
       │ バナー → Stripe Checkout          │
       │                                  │
       └─────────────┬────────────────────┘
                     ▼
         [Stripe Subscription]
                     │
                     │ invoice.payment_succeeded
                     ▼
         [sedori GAS doPost]   ← 次フェーズで実装
                     │
                     ▼
    [sedori スプシ licenses シート]
         に行追加（PRO-2026-XXXX）
                     ▼
         [顧客にメールでライセンスキー送付]
                     ▼
         顧客がツールを起動して使用開始
```

## ファイル変更点

| ファイル | 追加した内容 |
|---------|-------------|
| `streamlit_new_item.py` | `ENABLE_SEDORI` フラグ + `SEDORI_PLANS` 定義 + 契約中ユーザー向けクロスセルバナー（3プランの Checkout ボタン） |
| `streamlit_admin.py` | `ENABLE_SEDORI` フラグ + サイドバーメニュー「せどりツール利用状況」+ `show_sedori_dashboard()` 関数 |

## feature flag の挙動

```python
# 両ファイル冒頭の定数セクションに同じ実装
try:
    ENABLE_SEDORI = bool(st.secrets.get("sedori", {}).get("enabled", False))
except Exception:
    ENABLE_SEDORI = os.environ.get("ENABLE_SEDORI", "false").lower() == "true"
```

| 環境 | 設定方法 | 結果 |
|------|---------|------|
| ローカル検証 | `ENABLE_SEDORI=true streamlit run streamlit_new_item.py` | 即表示 |
| Streamlit Cloud（本番）| Secrets に `[sedori] enabled = true` を追加 → アプリを再起動 | デプロイOK時に切替 |
| 何もしない（デフォルト）| - | sedori 機能は完全に非表示。既存運用に影響なし |

> **main にコミットしても本番には出ない設計**。デプロイは Streamlit Cloud の Secrets で制御。

## デプロイのタイミングで本番化する手順

1. Stripe で 4商品作成（→ [sedori-tool-package のガイド](../../sedori-tool-package/doc/ライセンス発行運用ガイド.md)）
2. 発行された **price_id** を取得：`price_xxxx_pricedown`, `price_xxxx_arrival`, `price_xxxx_full`, `price_xxxx_all`
3. Streamlit Cloud の **Secrets** を編集（Settings → Secrets）：

```toml
[sedori]
enabled = true
price_id_pricedown  = "price_xxxx_pricedown"
price_id_arrival    = "price_xxxx_arrival"
price_id_sedori_full = "price_xxxx_sedori_full"
price_id_all_full   = "price_xxxx_all_full"
```

4. 「Save」 → 「Reboot app」 → クロスセルバナーが既存ユーザーに表示開始

## ロールバック

問題が出たら Secrets で `enabled = false` に戻す → Reboot。
即座にバナー非表示、既存運用に戻る。

## 検証

ローカルで `ENABLE_SEDORI=true` を付けて起動 → 既存EC契約中アカウントでログイン →
「プラン契約・解約」 メニューを開く → クロスセルバナーが見えれば OK。

管理者アカウントでログイン → サイドバー「せどりツール利用状況」が見えれば OK。

## 次の実装フェーズ

- [ ] GAS の `gas/Code.gs` に `doPost()` を追加して Stripe Webhook を受け、
      自動で sedori スプシ `licenses` シートに行追加 + メール送信
- [ ] 顧客向けメール本文テンプレを作成（ライセンスキー + 設定手順URL）
- [ ] index.html のランディングに sedori 紹介セクション
- [ ] sedori 利用状況ダッシュボードに「契約後 30日 retention」「解約率」を追加
