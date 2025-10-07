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