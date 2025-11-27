import streamlit as st
import pymysql
import ssl
import ast
import json
import time
from datetime import datetime

# =========================================================================
# 👇 必须放在第一行
# =========================================================================
st.set_page_config(page_title="消防刷题Pro", page_icon="🔥", layout="centered", initial_sidebar_state="collapsed")

# =========================================================================
# 👇 数据库配置与连接
# =========================================================================
TIDB_CONFIG = {
    "host": "gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
    "port": 4000,
    "user": "2emKBRzbZrLBNax.root",
    "password": "Bh2VO3dlAEnhbv4G",
    "database": "test",
}

@st.cache_resource
def get_db_pool():
    try:
        return pymysql.connect(**TIDB_CONFIG, ssl={"check_hostname": False, "verify_mode": ssl.CERT_NONE}, autocommit=True, connect_timeout=3)
    except: return None

# =========================================================================
# 👇 进度保存与读取 (核心升级)
# =========================================================================
def init_progress_table():
    """确保数据库有存档表"""
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            # 创建一个表来存 JSON 格式的进度
            c.execute("""
                CREATE TABLE IF NOT EXISTS exam_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(50) DEFAULT 'admin', 
                    session_data LONGTEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)

def save_progress_and_pause():
    """【暂停】逻辑：保存当前所有状态到数据库"""
    if not st.session_state.q_list: return

    # 计算当前耗时
    elapsed = int(time.time() - st.session_state.start_time) + st.session_state.get('previous_elapsed', 0)
    
    # 打包数据
    state_dump = {
        "q_list": st.session_state.q_list,          # 题目列表
        "idx": st.session_state.idx,                # 当前做到第几题
        "user_answers": st.session_state.user_answers, # 已填答案
        "elapsed_seconds": elapsed,                 # 已用时间
        "score": st.session_state.get('score', 0)
    }
    
    conn = get_db_pool()
    if conn:
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as c:
                # 简单起见，我们只存一条记录，用 user_id='admin' 覆盖更新
                # 先删后插，或者用 UPDATE
                c.execute("DELETE FROM exam_progress WHERE user_id='admin'")
                c.execute("INSERT INTO exam_progress (user_id, session_data) VALUES (%s, %s)", 
                          ('admin', json.dumps(state_dump)))
            st.toast("✅ 进度已保存！")
            time.sleep(1)
            st.session_state.page = "home" # 返回首页
            st.rerun()
        except Exception as e:
            st.error(f"存档失败: {e}")

def load_progress():
    """【恢复】逻辑：从数据库读取存档"""
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("SELECT session_data FROM exam_progress WHERE user_id='admin' ORDER BY updated_at DESC LIMIT 1")
            row = c.fetchone()
            if row:
                data = json.loads(row[0])
                st.session_state.q_list = data['q_list']
                st.session_state.idx = data['idx']
                st.session_state.user_answers = {int(k): v for k, v in data['user_answers'].items()} # JSON key是str，转回int
                st.session_state.previous_elapsed = data['elapsed_seconds'] # 记录之前的耗时
                st.session_state.start_time = time.time() # 重新开始计时
                st.session_state.page = "quiz"
                st.rerun()
    st.toast("未找到存档")

def check_has_progress():
    """检查是否有未完成的进度"""
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("SELECT count(*) FROM exam_progress WHERE user_id='admin'")
            return c.fetchone()[0] > 0
    return False

def clear_progress():
    """练习完成时，删除存档"""
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM exam_progress WHERE user_id='admin'")

# =========================================================================
# 👇 辅助功能
# =========================================================================
def save_record_background(q_id, user_ans, is_correct):
    if 'unsaved_records' not in st.session_state: st.session_state.unsaved_records = []
    st.session_state.unsaved_records.append({"qid": q_id, "ans": user_ans, "ok": 1 if is_correct else 0, "time": datetime.now()})
    if len(st.session_state.unsaved_records) >= 3 or not is_correct: sync_to_db()

def sync_to_db():
    records = st.session_state.get('unsaved_records', [])
    if not records: return
    conn = get_db_pool()
    if conn:
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as c:
                sql = "INSERT INTO study_record (question_id, user_answer, is_correct, study_date) VALUES (%s, %s, %s, %s)"
                c.executemany(sql, [(r['qid'], r['ans'], r['ok'], r['time']) for r in records])
            st.session_state.unsaved_records = []
        except: pass

@st.cache_data(ttl=600)
def fetch_questions(source_type, limit=50):
    conn = get_db_pool()
    if not conn: return []
    questions = []
    try:
        conn.ping(reconnect=True)
        with conn.cursor() as c:
            if source_type == "mistake":
                sql = "SELECT DISTINCT q.id, q.question, q.options, q.answer, q.explanation, q.beginner_guide FROM question_bank q JOIN study_record s ON q.id=s.question_id WHERE s.is_correct=0 ORDER BY s.study_date DESC LIMIT %s"
                c.execute(sql, (limit,))
            else:
                sql = "SELECT id, question, options, answer, explanation, beginner_guide FROM question_bank WHERE source_type=%s ORDER BY RAND() LIMIT %s"
                c.execute(sql, (source_type, limit))
            for row in c.fetchall():
                try: opts = json.loads(row[2]) if '[' in row[2] else ast.literal_eval(row[2])
                except: opts = [str(row[2])]
                if not isinstance(opts, list): opts = [str(opts)]
                questions.append({"id": row[0], "q": row[1], "opts": opts, "ans": row[3], "exp": row[4], "guide": row[5]})
    except: pass
    return questions

# =========================================================================
# 👇 UI 样式
# =========================================================================
st.markdown("""
<style>
    .top-bar { display: flex; justify-content: space-between; align-items: center; background: #fff; padding: 10px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 15px; }
    .stButton>button { border-radius: 20px; font-weight: bold; }
    .res-box { padding: 15px; border-radius: 10px; margin-top: 10px; animation: fadeIn 0.5s; }
    .res-ok { background: #d1fae5; border: 1px solid #34d399; color: #064e3b; }
    .res-no { background: #fee2e2; border: 1px solid #f87171; color: #7f1d1d; }
    .opt-div { padding: 10px; margin: 5px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: white; }
    .opt-correct { background: #dcfce7; border-color: #22c55e; }
    .opt-wrong { background: #fee2e2; border-color: #ef4444; }
    @keyframes fadeIn { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:translateY(0); } }
</style>
""", unsafe_allow_html=True)

# 初始化
if 'page' not in st.session_state: st.session_state.page = "home"
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'start_time' not in st.session_state: st.session_state.start_time = time.time()
if 'previous_elapsed' not in st.session_state: st.session_state.previous_elapsed = 0 # 之前累计的时间

init_progress_table() # 确保表存在

# =========================================================================
# 👇 首页
# =========================================================================
if st.session_state.page == "home":
    st.title("🔥 消防大脑 Pro")
    
    # 检查是否有存档
    has_save = check_has_progress()
    if has_save:
        st.info("检测到您有未完成的练习")
        if st.button("▶️ 继续上次练习", type="primary", use_container_width=True):
            load_progress()
    
    st.divider()
    st.caption("开始新练习")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📚 普通资料", use_container_width=True):
            st.session_state.q_list = fetch_questions("普通资料", 50)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.user_answers = {}
            st.session_state.start_time = time.time()
            st.session_state.previous_elapsed = 0
            st.rerun()
    with col2:
        if st.button("💯 历年真题", use_container_width=True):
            st.session_state.q_list = fetch_questions("历年真题", 50)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.user_answers = {}
            st.session_state.start_time = time.time()
            st.session_state.previous_elapsed = 0
            st.rerun()

    if st.button("📒 错题本 (复习)", use_container_width=True):
        st.session_state.q_list = fetch_questions("mistake", 30)
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.user_answers = {}
        st.session_state.start_time = time.time()
        st.session_state.previous_elapsed = 0
        st.rerun()

# =========================================================================
# 👇 做题界面
# =========================================================================
elif st.session_state.page == "quiz":
    if not st.session_state.q_list:
        st.warning("暂无题目")
        if st.button("返回"): st.session_state.page = "home"; st.rerun()
        st.stop()

    # 1. 顶部栏 (计时与暂停)
    # 累计时间 = 之前的存档时间 + (现在 - 这次开始的时间)
    total_seconds = int(st.session_state.previous_elapsed + (time.time() - st.session_state.start_time))
    time_str = f"{total_seconds//60:02d}:{total_seconds%60:02d}"
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        # 返回其实就是暂停存档，为了防止误触，我们把逻辑一致化
        if st.button("🏠 保存退出"):
            save_progress_and_pause()
    with c2:
        st.markdown(f"<div style='text-align:center; font-size:20px; font-weight:bold; color:#555;'>⏱️ {time_str}</div>", unsafe_allow_html=True)
    with c3:
        # 真正的暂停按钮
        if st.button("⏸ 暂停"):
            save_progress_and_pause()

    # 2. 进度与题目
    q_data = st.session_state.q_list
    total = len(q_data)
    idx = st.session_state.idx
    current_q = q_data[idx]
    
    st.progress((idx + 1) / total)
    st.markdown(f"**第 {idx + 1}/{total} 题**")
    st.markdown(f"### {current_q['q']}")

    # 3. 交互逻辑
    has_answered = idx in st.session_state.user_answers
    user_choice = st.session_state.user_answers.get(idx)

    if not has_answered:
        choice = st.radio("请选择:", current_q['opts'], index=None, key=f"radio_{idx}", label_visibility="collapsed")
        
        b1, b2 = st.columns([1, 1])
        with b1:
            if idx > 0:
                if st.button("⬅️ 上一题"):
                    st.session_state.idx -= 1
                    st.rerun()
            else:
                st.button("⬅️ 上一题", disabled=True)
        with b2:
            if st.button("提交 ✅", type="primary", use_container_width=True):
                if choice:
                    st.session_state.user_answers[idx] = choice
                    real_ans = current_q['ans'].strip().upper()
                    my_ans = choice[0].strip().upper()
                    is_correct = (real_ans == my_ans)
                    save_record_background(current_q['id'], my_ans, is_correct)
                    st.rerun()
                else:
                    st.toast("请选择一个选项")
    else:
        # 结果页
        real_ans = current_q['ans'].strip().upper()
        my_ans = user_choice[0].strip().upper()
        is_correct = (real_ans == my_ans)

        # 渲染选项
        for opt in current_q['opts']:
            opt_char = opt[0].strip().upper()
            style = "opt-div"
            if opt_char == real_ans:
                style += " opt-correct"
                opt = "✅ " + opt
            elif opt_char == my_ans and not is_correct:
                style += " opt-wrong"
                opt = "❌ " + opt
            
            st.markdown(f"<div class='{style}'>{opt}</div>", unsafe_allow_html=True)

        # 解析区域
        box_cls = "res-ok" if is_correct else "res-no"
        title = "回答正确！🎉" if is_correct else f"回答错误！正确答案：{real_ans}"
        
        # 渲染解析文本（处理换行）
        exp_text = current_q['exp'].replace("\n", "<br>")
        
        st.markdown(f"""
        <div class='res-box {box_cls}'>
            <h4>{title}</h4>
            <hr style='opacity:0.2'>
            <p><b>🔍 深度解析：</b><br>{exp_text}</p>
            <p style='margin-top:10px; font-size:14px; color:#666;'><b>🍬 助记技巧：</b>{current_q['guide']}</p>
        </div>
        """, unsafe_allow_html=True)

        # 导航
        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("⬅️ 上一题", key="p_done"):
                st.session_state.idx -= 1
                st.rerun()
        with b2:
            if idx < total - 1:
                if st.button("下一题 ➡️", type="primary", key="n_done", use_container_width=True):
                    st.session_state.idx += 1
                    st.rerun()
            else:
                if st.button("完成练习 🏆", type="primary", use_container_width=True):
                    sync_to_db()
                    clear_progress() # 清除存档
                    st.balloons()
                    st.success("练习结束！")
                    time.sleep(2)
                    st.session_state.page = "home"
                    st.rerun()
