import streamlit as st
import pymysql
import ssl
import ast
import json
import time
from datetime import datetime
import streamlit.components.v1 as components

# =========================================================================
# 👇 1. 必须放在第一行
# =========================================================================
st.set_page_config(page_title="消防刷题Pro", page_icon="🔥", layout="centered", initial_sidebar_state="collapsed")

# =========================================================================
# 👇 2. 数据库配置
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
# 👇 3. 核心修复：暴力解析选项 (解决ABCD挤一坨的问题)
# =========================================================================
def safe_parse_options(raw_data):
    """
    不管数据库里存的是啥格式，都强制拆解成干净的列表
    """
    if not raw_data: return []
    
    # 1. 如果已经是列表
    if isinstance(raw_data, list):
        # 再次检查列表里是不是混入了奇怪的字符串，比如 ["['A','B']"]
        if len(raw_data) == 1 and isinstance(raw_data[0], str) and ("A." in raw_data[0] or "[" in raw_data[0]):
            return safe_parse_options(raw_data[0])
        return raw_data

    # 2. 如果是字符串
    if isinstance(raw_data, str):
        # 去掉首尾可能的方括号和引号
        clean = raw_data.strip().strip('"').strip("'")
        if clean.startswith("[") and clean.endswith("]"):
            try:
                # 尝试标准解析
                res = ast.literal_eval(clean)
                if isinstance(res, list): return safe_parse_options(res)
            except:
                pass
        
        # 3. 实在解不开，直接暴力字符串分割
        # 比如 "A. xxx B. xxx" 或者 "['A. xxx', 'B. xxx']"
        # 先去掉括号和引号
        clean_str = raw_data.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
        # 如果有逗号分隔
        if "," in clean_str:
            return [x.strip() for x in clean_str.split(",")]
        # 如果没有逗号，尝试按 A. B. C. D. 分割（这里简化处理，假设有逗号或格式标准）
        return [clean_str]
    
    return []

# =========================================================================
# 👇 4. 实时计时器 (解决时间不走字的问题)
# =========================================================================
def show_realtime_timer(initial_seconds):
    """
    注入 JavaScript，让时间真的'动'起来，而不是点一下才跳一下
    """
    timer_html = f"""
    <div style="
        font-size: 20px; 
        font-weight: bold; 
        color: #555; 
        text-align: center; 
        padding: 5px; 
        margin-bottom: 10px;
    ">
        ⏱️ <span id="timer">00:00</span>
    </div>
    <script>
        let totalSeconds = {initial_seconds};
        function updateTimer() {{
            totalSeconds++;
            let m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
            let s = (totalSeconds % 60).toString().padStart(2, '0');
            let el = document.getElementById('timer');
            if(el) {{ el.innerText = m + ':' + s; }}
        }}
        // 首次立即执行
        let m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        let s = (totalSeconds % 60).toString().padStart(2, '0');
        let el = document.getElementById('timer');
        if(el) {{ el.innerText = m + ':' + s; }}
        
        // 每秒更新
        setInterval(updateTimer, 1000);
    </script>
    """
    components.html(timer_html, height=50)

# =========================================================================
# 👇 5. 存档与做题逻辑
# =========================================================================
def init_progress_table():
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS exam_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(50) DEFAULT 'admin', 
                    session_data LONGTEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)

def save_and_exit():
    """保存并退出"""
    if not st.session_state.q_list: return
    
    # 计算实际经过的时间
    elapsed = int(time.time() - st.session_state.start_time) + st.session_state.previous_elapsed
    
    state_dump = {
        "q_list": st.session_state.q_list,
        "idx": st.session_state.idx,
        "user_answers": st.session_state.user_answers,
        "elapsed_seconds": elapsed,
        "score": st.session_state.get('score', 0)
    }
    
    conn = get_db_pool()
    if conn:
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as c:
                c.execute("DELETE FROM exam_progress WHERE user_id='admin'")
                c.execute("INSERT INTO exam_progress (user_id, session_data) VALUES (%s, %s)", ('admin', json.dumps(state_dump)))
            st.toast("✅ 进度已保存")
            time.sleep(0.5)
            st.session_state.page = "home"
            st.rerun()
        except: pass

def load_progress():
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("SELECT session_data FROM exam_progress WHERE user_id='admin' ORDER BY updated_at DESC LIMIT 1")
            row = c.fetchone()
            if row:
                data = json.loads(row[0])
                st.session_state.q_list = data['q_list']
                st.session_state.idx = data['idx']
                # 修复 int key 变 str 问题
                st.session_state.user_answers = {int(k): v for k, v in data['user_answers'].items()}
                st.session_state.previous_elapsed = data['elapsed_seconds']
                st.session_state.start_time = time.time()
                st.session_state.page = "quiz"
                st.rerun()

def check_has_progress():
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("SELECT count(*) FROM exam_progress WHERE user_id='admin'")
            row = c.fetchone()
            return row[0] > 0 if row else False
    return False

def clear_progress():
    conn = get_db_pool()
    if conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM exam_progress WHERE user_id='admin'")

def save_mistake_background(q_id, user_ans, is_correct):
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
                # 🔥 关键：调用暴力解析器
                opts = safe_parse_options(row[2])
                questions.append({"id": row[0], "q": row[1], "opts": opts, "ans": row[3], "exp": row[4], "guide": row[5]})
    except: pass
    return questions

# =========================================================================
# 👇 6. 界面与逻辑
# =========================================================================

# 样式
st.markdown("""
<style>
    .stButton>button { border-radius: 20px; font-weight: bold; width: 100%; }
    .res-box { padding: 15px; border-radius: 10px; margin-top: 10px; animation: fadeIn 0.5s; }
    .res-ok { background: #d1fae5; border: 1px solid #34d399; color: #064e3b; }
    .res-no { background: #fee2e2; border: 1px solid #f87171; color: #7f1d1d; }
    .opt-div { padding: 12px; margin: 8px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: white; font-size:16px; }
    .opt-correct { background: #dcfce7; border-color: #22c55e; }
    .opt-wrong { background: #fee2e2; border-color: #ef4444; }
    @keyframes fadeIn { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:translateY(0); } }
</style>
""", unsafe_allow_html=True)

# 状态初始化
if 'page' not in st.session_state: st.session_state.page = "home"
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'start_time' not in st.session_state: st.session_state.start_time = time.time()
if 'previous_elapsed' not in st.session_state: st.session_state.previous_elapsed = 0
if 'q_list' not in st.session_state: st.session_state.q_list = []
if 'idx' not in st.session_state: st.session_state.idx = 0

init_progress_table()

# --- 首页 ---
if st.session_state.page == "home":
    st.title("🔥 消防大脑 Pro")
    
    if check_has_progress():
        st.info("检测到您有未完成的练习")
        if st.button("▶️ 继续上次练习", type="primary"):
            load_progress()
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📚 普通资料"):
            st.session_state.q_list = fetch_questions("普通资料", 50)
            if not st.session_state.q_list:
                st.error("题库为空，请先在电脑端导入数据")
            else:
                st.session_state.page = "quiz"
                st.session_state.idx = 0
                st.session_state.user_answers = {}
                st.session_state.start_time = time.time()
                st.session_state.previous_elapsed = 0
                st.rerun()
    with col2:
        if st.button("💯 历年真题"):
            st.session_state.q_list = fetch_questions("历年真题", 50)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.user_answers = {}
            st.session_state.start_time = time.time()
            st.session_state.previous_elapsed = 0
            st.rerun()

    if st.button("📒 错题本"):
        st.session_state.q_list = fetch_questions("mistake", 30)
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.user_answers = {}
        st.session_state.start_time = time.time()
        st.session_state.previous_elapsed = 0
        st.rerun()

# --- 做题页 ---
elif st.session_state.page == "quiz":
    if not st.session_state.q_list:
        st.warning("暂无题目")
        if st.button("返回"): st.session_state.page = "home"; st.rerun()
        st.stop()

    # 计算当前累积时间传给前端 JS
    current_elapsed = int(st.session_state.previous_elapsed + (time.time() - st.session_state.start_time))
    
    # 顶部栏
    c1, c2, c3 = st.columns([1.2, 2, 1])
    with c1:
        if st.button("🏠 保存退出"): save_and_exit()
    with c2:
        # 🔥 这里调用 JS 计时器
        show_realtime_timer(current_elapsed)
    with c3:
        if st.button("⏸ 暂停"): save_and_exit()

    # 题目区域
    q_data = st.session_state.q_list
    total = len(q_data)
    idx = st.session_state.idx
    current_q = q_data[idx]
    
    st.progress((idx + 1) / total)
    st.markdown(f"**第 {idx + 1}/{total} 题**")
    st.markdown(f"### {current_q['q']}")

    has_answered = idx in st.session_state.user_answers
    user_choice = st.session_state.user_answers.get(idx)

    # 选项显示
    if not has_answered:
        # 即使这里 current_q['opts'] 只有1个元素，radio也能正常显示
        choice = st.radio("请选择:", current_q['opts'], index=None, key=f"radio_{idx}", label_visibility="collapsed")
        
        b1, b2 = st.columns([1, 1])
        with b1:
            if idx > 0:
                if st.button("⬅️ 上一题"):
                    st.session_state.idx -= 1
                    st.rerun()
        with b2:
            if st.button("提交 ✅", type="primary"):
                if choice:
                    st.session_state.user_answers[idx] = choice
                    real_ans = current_q['ans'].strip().upper()
                    # 提取选项首字母 (兼容 "A. 内容" 和 "A" 两种格式)
                    my_ans = choice.strip()[0].upper()
                    is_correct = (real_ans == my_ans)
                    save_mistake_background(current_q['id'], my_ans, is_correct)
                    st.rerun()
                else:
                    st.toast("请选择一个选项")
    else:
        # 已回答：显示解析
        real_ans = current_q['ans'].strip().upper()
        my_ans_full = user_choice
        my_ans = my_ans_full.strip()[0].upper()
        is_correct = (real_ans == my_ans)

        for opt in current_q['opts']:
            opt_char = opt.strip()[0].upper()
            style = "opt-div"
            prefix = ""
            if opt_char == real_ans:
                style += " opt-correct"
                prefix = "✅ "
            elif opt_char == my_ans and not is_correct:
                style += " opt-wrong"
                prefix = "❌ "
            
            st.markdown(f"<div class='{style}'>{prefix}{opt}</div>", unsafe_allow_html=True)

        box_cls = "res-ok" if is_correct else "res-no"
        title = "回答正确！🎉" if is_correct else f"回答错误！正确答案：{real_ans}"
        
        st.markdown(f"""
        <div class='res-box {box_cls}'>
            <h4>{title}</h4>
            <hr style='opacity:0.2'>
            <p><b>🔍 深度解析：</b><br>{current_q['exp']}</p>
            <p style='margin-top:10px; font-size:14px; color:#666;'><b>🍬 记忆技巧：</b>{current_q['guide']}</p>
        </div>
        """, unsafe_allow_html=True)

        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("⬅️ 上一题", key="p_done"):
                st.session_state.idx -= 1
                st.rerun()
        with b2:
            if idx < total - 1:
                if st.button("下一题 ➡️", type="primary", key="n_done"):
                    st.session_state.idx += 1
                    st.rerun()
            else:
                if st.button("完成练习 🏆", type="primary"):
                    sync_to_db()
                    clear_progress()
                    st.balloons()
                    st.success("练习结束！")
                    time.sleep(2)
                    st.session_state.page = "home"
                    st.rerun()
