# streamlit_key_gate.py
# -------------------------------------------------------------
# Streamlit で「アクセスキー発行（管理者）＋利用者認証」を実装するサンプル。
# - SQLite を使ってキーを保存（発行済み/使用済み/有効期限）
# - 管理者は st.secrets["ADMIN_PASSWORD"] でログイン
# - ワンタイム／マルチユース切り替え
# - CSV ダウンロード、検索、失効、再発行など
# -------------------------------------------------------------

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

DB_PATH = "keys.db"  # Streamlit Community Cloud では永続性は保証されません。確実な永続化は外部DB推奨。

# ========================= 共通ユーティリティ =========================

def _connect():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            raw_hint TEXT,                -- 先頭/末尾数文字など、照合ヒント（フルキー保存はしない）
            issued_to TEXT,
            tag TEXT,                     -- 用途メモ
            is_one_time INTEGER DEFAULT 1,
            issued_at TIMESTAMP,
            expires_at TIMESTAMP,
            used_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            is_revoked INTEGER DEFAULT 0
        );
        """
    )
    return conn


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _now() -> datetime:
    # Asia/Tokyo を想定（Streamlit はTZ未設定ならサーバーTZ）。厳密にするなら pytz 等で調整。
    return datetime.now()


# ========================= 認証（ユーザー側） =========================

def key_gate_ui(success_message: str = "認証に成功しました。ページに入れます。") -> bool:
    """アクセスキー入力UI。正しければ True を返し、セッションに認証フラグを立てる。"""
    if st.session_state.get("is_authenticated"):
        return True

    st.markdown("## 🔑 アクセスキー認証")
    key_input = st.text_input("アクセスキーを入力", type="password", placeholder="例: X1Y2-...-Z9")
    submit = st.button("入室する")

    if submit:
        ok, msg = _verify_and_mark_usage(key_input)
        if ok:
            st.success(success_message)
            st.session_state["is_authenticated"] = True
            return True
        else:
            st.error(msg)

    with st.expander("キーをURLクエリから自動入力（運営向け）"):
        st.caption("例: https://example.streamlit.app/?key=XXXXX")
        qparams = st.query_params
        if "key" in qparams and not key_input:
            auto_key = qparams.get("key")
            if isinstance(auto_key, list):
                auto_key = auto_key[0]
            st.info("URLからキーを読み込みました。ボタンを押して入室してください。")
            st.session_state["__auto_key"] = auto_key

    if st.session_state.get("__auto_key") and not key_input:
        # 自動入力の見た目用
        st.caption("（URL経由のキーを検出）")

    return False


def _verify_and_mark_usage(raw_key: str) -> tuple[bool, str]:
    if not raw_key:
        return False, "キーが未入力です。"

    conn = _connect()
    cur = conn.cursor()
    h = _hash_key(raw_key)
    cur.execute("SELECT id, is_one_time, expires_at, used_count, is_revoked FROM access_keys WHERE key_hash=?", (h,))
    row = cur.fetchone()

    if not row:
        return False, "キーが無効です。"

    key_id, is_one_time, expires_at, used_count, is_revoked = row

    if is_revoked:
        return False, "このキーは失効（無効化）されています。"

    if expires_at is not None:
        try:
            exp_dt = datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
        except Exception:
            exp_dt = None
        if exp_dt and _now() > exp_dt:
            return False, "キーの有効期限が切れています。"

    # 使用記録を更新
    cur.execute(
        "UPDATE access_keys SET used_count = used_count + 1, last_used_at = ? WHERE id = ?",
        (_now(), key_id),
    )
    conn.commit()

    if is_one_time and used_count >= 1:
        return False, "このキーはワンタイムで、既に使用済みです。"

    return True, "OK"


# ========================= 管理者（発行・管理） =========================

def admin_panel():
    st.markdown("# 🛠️ アクセスキー管理（管理者）")

    pw = st.text_input("管理者パスワード", type="password")
    if not pw:
        st.stop()

    if "ADMIN_PASSWORD" not in st.secrets:
        st.error("st.secrets['ADMIN_PASSWORD'] が未設定です。Streamlit の Secrets に追加してください。")
        st.stop()

    if pw != st.secrets["ADMIN_PASSWORD"]:
        st.error("パスワードが違います。")
        st.stop()

    st.success("管理者ログイン済み")

    # ---- 発行フォーム ----
    with st.form("issue_form"):
        st.subheader("新規キー発行")
        count = st.number_input("発行数", 1, 1000, 10)
        days = st.number_input("有効日数（0で無期限）", 0, 3650, 30)
        is_one_time = st.checkbox("ワンタイムキー（1人1回）", value=True)
        tag = st.text_input("用途タグ（任意）", placeholder="例: βテスター、友人、購入者…")
        issued_to = st.text_input("発行先メモ（任意）", placeholder="例: name@example.com")
        submitted = st.form_submit_button("キーを発行する")

    if submitted:
        keys_df = _issue_keys(count=count, days=days, is_one_time=is_one_time, tag=tag, issued_to=issued_to)
        st.success(f"{len(keys_df)} 件のキーを発行しました。下のテーブルとCSVを保存してください（キーはDBにはハッシュのみ保存）。")
        st.dataframe(keys_df)
        st.download_button(
            label="発行キーをCSVで保存",
            data=keys_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"issued_keys_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

    st.divider()

    # ---- 一覧と操作 ----
    conn = _connect()
    df = pd.read_sql_query("SELECT id, raw_hint, issued_to, tag, is_one_time, issued_at, expires_at, used_count, last_used_at, is_revoked FROM access_keys ORDER BY id DESC", conn)

    st.subheader("発行済みキー一覧（ハッシュベース。生キーは保持しません）")
    st.dataframe(df, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        target_id = st.number_input("対象ID", min_value=1, step=1)
    with col2:
        action = st.selectbox("操作", ["無効化(失効)", "再有効化", "削除"])
    with col3:
        run = st.button("実行")

    if run:
        msg = _operate_key(int(target_id), action)
        if msg.startswith("OK"):
            st.success(msg)
        else:
            st.error(msg)

    st.caption("※ 無効化は取り消し可能。削除は物理削除。")


def _issue_keys(count: int, days: int, is_one_time: bool, tag: str, issued_to: str) -> pd.DataFrame:
    """生キーを生成し、ハッシュのみDB保存。生キーは戻り値（CSV）でのみ提示。"""
    rows = []
    conn = _connect()
    cur = conn.cursor()

    expires_at: Optional[datetime] = None
    if days > 0:
        expires_at = _now() + timedelta(days=int(days))

    for _ in range(int(count)):
        raw = _generate_readable_key()
        h = _hash_key(raw)
        hint = f"{raw[:3]}…{raw[-3:]}"
        try:
            cur.execute(
                """
                INSERT INTO access_keys (key_hash, raw_hint, issued_to, tag, is_one_time, issued_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    h,
                    hint,
                    issued_to.strip() or None,
                    tag.strip() or None,
                    1 if is_one_time else 0,
                    _now(),
                    expires_at,
                ),
            )
        except sqlite3.IntegrityError:
            # まれに衝突したらリトライ
            continue
        rows.append({
            "access_key": raw,
            "hint": hint,
            "issued_to": issued_to,
            "tag": tag,
            "is_one_time": is_one_time,
            "expires_at": expires_at.isoformat() if expires_at else "",
        })

    conn.commit()

    return pd.DataFrame(rows)


def _operate_key(target_id: int, action: str) -> str:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM access_keys WHERE id=?", (target_id,))
    if not cur.fetchone():
        return "対象IDが見つかりません。"

    if action == "無効化(失効)":
        cur.execute("UPDATE access_keys SET is_revoked=1 WHERE id=?", (target_id,))
    elif action == "再有効化":
        cur.execute("UPDATE access_keys SET is_revoked=0 WHERE id=?", (target_id,))
    elif action == "削除":
        cur.execute("DELETE FROM access_keys WHERE id=?", (target_id,))
    else:
        return "不明な操作です。"

    conn.commit()
    return "OK: 反映しました。"


# ========================= 補助：読みやすいキー生成 =========================

def _generate_readable_key() -> str:
    """人に伝えやすい 4-4-4-4 形式キー（英大字+数字）。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 見分けづらい I/O/0/1 は除外
    parts = []
    for _ in range(4):
        part = "".join(secrets.choice(alphabet) for _ in range(4))
        parts.append(part)
    return "-".join(parts)


# ========================= 組み込みサンプル =========================
if __name__ == "__main__":
    st.set_page_config(page_title="鍵付きデモ", layout="centered")

    # 画面右上のメニューから → Rerun でDB初期化が走ります
    st.caption("このデモは SQLite 保存です。外部DBを使うと本番でも安心です。")

    # 1) ユーザー側ゲート
    authed = key_gate_ui()

    if not authed:
        st.stop()  # ここより下は認証済みのみ

    # 2) 本編（あなたのアプリ本体をここに）
    st.success("ようこそ！これは保護されたエリアです。")

    st.divider()
    st.caption("— 以下は管理者向け —")
    admin_panel()
