# arashi_app_fixed.py — Cloud用：インデント修正版 + 鍵付き
# -------------------------------------------------------------
# 依存: streamlit, pandas, numpy, scikit-learn
# 同じフォルダに streamlit_key_gate.py（キー発行＆認証モジュール） を置いてください。
# Streamlit Cloud の Secrets に ADMIN_PASSWORD を設定してください。
# -------------------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# --- 鍵ゲートの取り込み ---
try:
    from streamlit_key_gate import key_gate_ui, admin_panel
except Exception:
    st.error("キー認証モジュールが見つかりません。streamlit_key_gate.py をレポジトリ直下に置いてください。")
    st.stop()

st.set_page_config(page_title="ARASHI (鍵付き・修正版)", layout="centered")

# === 管理者パネルの表示導線（サイドバー/クエリ/トップボタン） ===
# 1) サイドバーのチェックボックス
st.sidebar.markdown("## 🔐 管理者")
admin_mode = st.sidebar.checkbox(
    "管理者モードを開く",
    value=False,
    help="キーが無くても、管理者パスワードでパネルを開けます。",
)

# 2) URLクエリ ?admin=1 対応（新旧API互換）
get_admin = None
try:
    q = st.query_params
    get_admin = q.get("admin")
except Exception:
    if hasattr(st, "experimental_get_query_params"):
        q = st.experimental_get_query_params()
        get_admin = q.get("admin")

if isinstance(get_admin, list):
    get_admin = get_admin[0]
if get_admin == "1":
    admin_mode = True

# 3) メインエリアに予備ボタン（サイドバーが見えない場合の導線）
colA, colB = st.columns([1, 3])
with colA:
    if st.button("🔐 管理者モードを開く", help="サイドバーが表示されない場合はこちら"):
        admin_mode = True

if admin_mode:
    st.markdown("# 🛠️ 管理者パネル")
    admin_panel()
    st.stop()

# === まずは鍵認証（利用者用） ===
if not key_gate_ui("認証に成功しました。ARASHIへ入室します。"):
    st.info("管理者の方は、サイドバーの『管理者モードを開く』か URL に ?admin=1 を付けて入ってください。")
    st.stop()

# ===== ここから下が ARASHI 本編 =====

st.markdown(
    """
    <h1 style='text-align: center;'>🌪️ ARASHI 🌪️</h1>
    """,
    unsafe_allow_html=True,
)

st.markdown("---")  # 区切り線

# --- セッション初期化 ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- 結果入力 ---
st.write("### 結果を入力してください")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🟦 Player 勝ち"):
        st.session_state.history.append("Player")
with col2:
    if st.button("🟥 Banker 勝ち"):
        st.session_state.history.append("Banker")
with col3:
    if st.button("🟩 Tie"):
        st.session_state.history.append("Tie")

# --- 履歴表示 ---
if len(st.session_state.history) == 0:
    st.info("まずは結果を入力してください。")
    st.stop()

df = pd.DataFrame(st.session_state.history, columns=["Result"])
st.write("### 📊 履歴（最新5件）")
st.table(df.tail(5))

# --- エンコード関数 ---
def encode_result(result: str):
    if result == "Player":
        return 0
    elif result == "Banker":
        return 1
    else:
        return None

# --- 特徴量作成 ---
def create_features(history, window: int = 3):
    encoded = [encode_result(r) for r in history]
    filtered = [e for e in encoded if e is not None]
    X, y = [], []
    if len(filtered) <= window:
        return np.array([]), np.array([])
    for i in range(window, len(filtered)):
        last = filtered[i - window : i]
        target = filtered[i]
        # 特徴量作成
        avg = float(np.mean(last))
        streak = 1
        for j in range(len(last) - 1, 0, -1):
            if last[j] == last[j - 1]:
                streak += 1
            else:
                break
        alternations = sum(1 for j in range(1, len(last)) if last[j] != last[j - 1])
        alt_ratio = alternations / (len(last) - 1)
        X.append(last + [avg, streak, alt_ratio])
        y.append(target)
    return np.array(X), np.array(y)

# --- 特徴量生成 ---
X, y = create_features(st.session_state.history)

if len(y) < 10:
    st.warning("データが少ないため、AIを学習できません（最低10件以上必要です）")
    st.stop()

# --- 学習 ---
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42
)
model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X_train, y_train)
acc = accuracy_score(y_test, model.predict(X_test))
st.success(f"✅ モデル学習完了！ テスト精度: {acc:.2f}")
st.caption("※ Tie は学習に含まれません。Player / Banker の二択です。")

# --- 予測 ---
filtered_history = [
    encode_result(r) for r in st.session_state.history if encode_result(r) is not None
]
if len(filtered_history) >= 3:
    recent = filtered_history[-3:]
    avg = float(np.mean(recent))
    streak = 1
    for j in range(len(recent) - 1, 0, -1):
        if recent[j] == recent[j - 1]:
            streak += 1
        else:
            break
    alternations = sum(1 for j in range(1, len(recent)) if recent[j] != recent[j - 1])
    alt_ratio = alternations / 2
    features = np.array(recent + [avg, streak, alt_ratio]).reshape(1, -1)

    probs = model.predict_proba(features)[0]
    pred = int(np.argmax(probs))
    label = "Player" if pred == 0 else "Banker"
    confidence = float(probs[pred] * 100)

    color = "blue" if label == "Player" else "red"

    st.markdown(
        f"""
        <h3 style='text-align: center;'>
            ➡️ <span style='color: {color}; font-weight: bold;'>{label}</span>
        </h3>
        """,
        unsafe_allow_html=True,
    )

    st.progress(int(confidence))
    st.metric("予測の信頼度（確率）", f"{confidence:.1f}%")
else:
    st.warning("データが少ないため、予測を行うには最低3件の有効履歴が必要です。")

# --- リセットボタン ---
if st.button("🔄 履歴リセット"):
    st.session_state.history.clear()
    st.rerun()

# ===== 管理者パネル（任意で下に表示） =====
st.divider()
st.caption("— 以下は管理者向け（鍵の発行・失効・再有効化） —")
admin_panel()