# streamlit_key_gate.py


st.caption(※ 無効化は取り消し可能。削除は物理削除。)




def _issue_keys(count int, days int, is_one_time bool, tag str, issued_to str) - pd.DataFrame
rows = []
conn = _connect()
cur = conn.cursor()


expires_at Optional[datetime] = None
if days  0
expires_at = _now() + timedelta(days=int(days))


for _ in range(int(count))
raw = _generate_readable_key()
h = _hash_key(raw)
hint = f{raw[3]}…{raw[-3]}
try
cur.execute(

INSERT INTO access_keys (key_hash, raw_hint, issued_to, tag, is_one_time, issued_at, expires_at)
VALUES (, , , , , , )
,
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
except sqlite3.IntegrityError
continue
rows.append({
access_key raw,
hint hint,
issued_to issued_to,
tag tag,
is_one_time is_one_time,
expires_at expires_at.isoformat() if expires_at else ,
})


conn.commit()
return pd.DataFrame(rows)




def _operate_key(target_id int, action str) - str
conn = _connect()
cur = conn.cursor()
cur.execute(SELECT id FROM access_keys WHERE id=, (target_id,))
if not cur.fetchone()
return 対象IDが見つかりません。


if action == 無効化(失効)
cur.execute(UPDATE access_keys SET is_revoked=1 WHERE id=, (target_id,))
elif action == 再有効化
cur.execute(UPDATE access_keys SET is_revoked=0 WHERE id=, (target_id,))
elif action == 削除
cur.execute(DELETE FROM access_keys WHERE id=, (target_id,))
else
return 不明な操作です。


conn.commit()
return OK 反映しました。




def _generate_readable_key() - str
alphabet = ABCDEFGHJKLMNPQRSTUVWXYZ23456789
parts = []
for _ in range(4)
part = .join(secrets.choice(alphabet) for _ in range(4))
parts.append(part)
return -.join(parts)

# arashi_app.py — アクセスキー発行＆認証を組み込んだ ARASHI 本体（Cloud向け）
avg = np.mean(last)
streak = 1
for j in range(len(last)-1, 0, -1):
if last[j] == last[j-1]:
streak += 1
else:
break
alternations = sum(1 for j in range(1, len(last)) if last[j] != last[j-1])
alt_ratio = alternations / (len(last)-1)
X.append(last + [avg, streak, alt_ratio])
y.append(target)
return np.array(X), np.array(y)


# --- 特徴量生成 ---
X, y = create_features(st.session_state.history)


if len(y) < 10:
st.warning("データが少ないため、AIを学習できません（最低10件以上必要です）")
st.stop()


# --- 学習 ---
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X_train, y_train)
acc = accuracy_score(y_test, model.predict(X_test))
st.success(f"✅ モデル学習完了！ テスト精度: {acc:.2f}")
st.caption("※ Tie は学習に含まれません。Player / Banker の二択です。")


# --- 予測 ---
filtered_history = [encode_result(r) for r in st.session_state.history if encode_result(r) is not None]
if len(filtered_history) >= 3:
recent = filtered_history[-3:]
avg = np.mean(recent)
streak = 1
for j in range(len(recent)-1, 0, -1):
if recent[j] == recent[j-1]:
streak += 1
else:
break
alternations = sum(1 for j in range(1, len(recent)) if recent[j] != recent[j-1])
alt_ratio = alternations / 2
features = np.array(recent + [avg, streak, alt_ratio]).reshape(1, -1)


probs = model.predict_proba(features)[0]
pred = np.argmax(probs)
label = "Player" if pred == 0 else "Banker"
confidence = probs[pred] * 100


color = "blue" if label == "Player" else "red"


st.markdown(
f"""
<h3 style='text-align: center;'>
➡️ <span style='color: {color}; font-weight: bold;'>{label}</span>
</h3>
""",
unsafe_allow_html=True
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