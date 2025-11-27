import streamlit as st
import pymysql
import ssl
import ast
import json
import time
import re
from datetime import datetime
import streamlit.components.v1 as components

# =========================================================================
# 👇 1. 核心配置 (保持第一行)
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
# 👇 3. 暴力选项解析器 (专门修复选项挤成一坨的问题)
# =========================================================================
def aggressive_parse_options(raw_data):
    """
    不管数据多脏，强行把 A. B. C. D. 拆开
    """
    if not raw_data: return []
    
    # 1. 预处理：转成字符串
    s = str(raw_data).strip()
    
    # 2. 如果已经是干净的列表（且长度大于1），直接返回
    # 但要防备 ["['A...','B...']"] 这种套娃
    if isinstance(raw_data, list):
        if len(raw_data) > 1: return raw_data
        if len(raw_data) == 1: s = str(raw_data[0]) # 剥开一层
    
    # 3. 清洗首尾的方括号和引号
    s = s.strip("[]").strip("'").strip('"')
    
    # 4. 尝试 AST 标准解析 (最理想情况)
    try:
        # 补回方括号尝试解析
        res = ast.literal_eval(f"[{s}]")
        if isinstance(res, list) and len(res) >= 2:
            return res
    except:
        pass

    # 5. 暴力正则分割 (针对截图中的情况)
    # 截图里是：'A. xxx', 'B. xxx' 这种格式
    # 我们用正则找 "', '" 或 '", "' 进行切割
    try:
        # 这种分割方式能处理绝大多数 python 字符串列表表示
        parts = re.split(r"',\s*'", s)
        if len(parts) == 1:
            parts = re.split(r'",\s*"', s)
            
        # 清理分割后残留的引号
        cleaned_parts = [p.strip("'").strip('"') for p in parts]
        
        # 兜底检测：如果分割失败，还是只有1个元素，且里面包含 A. B.
        if len(cleaned_parts) < 2 and "A." in s and "B." in s:
            # 最后的手段：按 A. B. C. D. 强行切位 (极少用到，但很管用)
            # 找 A. 的位置，B. 的位置...
            pass # 暂时信任正则分割，一般能解决 'A', 'B' 格式

        return cleaned_parts
    except:
        # 毁灭性兜底：如果全挂了，返回原始字符串让用户看见（虽然丑但能用）
        return [s]

# =========================================================================
# 👇 4. 实时计时器 (JS版)
# =========================================================================
def show_realtime_timer(initial_seconds):
    timer_html = f"""
    <div style="font-size: 20px; font-weight: bold; color: #444; text-align: center; margin-bottom: 15px;">
        ⏱️ <span id="timer_disp">00:00</span>
    </div>
    <script>
        let startSec = {initial_seconds};
        function tick() {{
            startSec++;
            let m = Math.floor(startSec / 60).toString().padStart(2, '0');
            let s = (startSec % 60).toString().padStart(2, '0');
            let el = document.getElementById('timer_disp');
            if(el) el.innerText = m + ':' + s;
        }}
        // 立即初始化
        let m = Math.floor(startSec / 60).toString().padStart(2, '0');
        let s = (startSec % 60).toString().padStart(2, '0');
        let el = document.getElementById('timer_disp');
        if(el) el.innerText = m + ':' + s;
        
        setInterval(tick, 1000);
    </script>
    """
    components.html(timer_html, height=40)

# =========================================================================
# 👇 5. 核心业务逻辑
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
    """保存进度并返回首页"""
    if not st.session_state.q_list: return
    
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
                # 🔥 调用暴力解析器
                opts = aggressive_parse_options(row[2])
                questions.append({"id": row[0], "q": row[1], "opts": opts, "ans": row[3], "exp": row[4], "guide": row[5]})
    except: pass
    return questions

# =========================================================================
# 👇 6. 界面渲染
# =========================================================================
st.markdown("""
<style>
    .stButton>button { border-radius: 8px; font-weight: bold; width: 100%; height: 45px; }
    .res-box { padding: 15px; border-radius: 10px; margin-top: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .res-ok { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
    .res-no { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
    .opt-div { padding: 12px 15px; margin: 8px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: white; font-size:16px; }
    .opt-correct { background: #dcfce7 !important; border-color: #22c55e !important; }
    .opt-wrong { background: #fee2e2 !important; border-color: #ef4444 !important; }
    /* 强制单选按钮样式 */
    .stRadio > div { gap: 10px; }
</style>
""", unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = "home"
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'start_time' not in st.session_state: st.session_state.start_time = time.time()
if 'previous_elapsed' not in st.session_state: st.session_state.previous_elapsed = 0
if 'q_list' not in st.session_state: st.session_state.q_list = []
if 'idx' not in st.session_state: st.session_state.idx = 0

init_progress_table()

# 🏠 首页
if st.session_state.page == "home":
    st.title("🔥 消防大脑 Pro")
    
    if check_has_progress():
        st.info("检测到您有未完成的练习")
        if st.button("▶️ 继续上次练习", type="primary"):
            load_progress()
    
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📚 普通资料"):
            st.session_state.q_list = fetch_questions("普通资料", 50)
            if not st.session_state.q_list: st.error("无题目数据")
            else:
                st.session_state.page = "quiz"
                st.session_state.idx = 0
                st.session_state.user_answers = {}
                st.session_state.start_time = time.time()
                st.session_state.previous_elapsed = 0
                st.rerun()
    with c2:
        if st.button("💯 历年真题"):
            st.session_state.q_list = fetch_questions("历年真题", 50)
            if not st.session_state.q_list: st.error("无题目数据")
            else:
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

# 📝 做题页
elif st.session_state.page == "quiz":
    if not st.session_state.q_list:
        st.warning("数据异常，请返回")
        if st.button("返回"): st.session_state.page = "home"; st.rerun()
        st.stop()

    current_elapsed = int(st.session_state.previous_elapsed + (time.time() - st.session_state.start_time))

    # 顶部导航
    c1, c2, c3 = st.columns([1.2, 2, 1])
    with c1: 
        if st.button("🏠 保存退出"): save_and_exit()
    with c2: 
        show_realtime_timer(current_elapsed)
    with c3: 
        if st.button("⏸ 暂停"): save_and_exit()

    # 进度与题目
    q_data = st.session_state.q_list
    total = len(q_data)
    idx = st.session_state.idx
    current_q = q_data[idx]
    
    st.progress((idx + 1) / total)
    st.markdown(f"**第 {idx + 1}/{total} 题**")
    st.markdown(f"### {current_q['q']}")

    has_answered = idx in st.session_state.user_answers
    user_choice = st.session_state.user_answers.get(idx)

    # 答题区
    if not has_answered:
        # 调试信息：如果选项还是没分开，这里会把长度打出来，方便排查
        # st.write(f"debug: len={len(current_q['opts'])}") 
        
        choice = st.radio("请选择:", current_q['opts'], index=None, key=f"radio_{idx}", label_visibility="collapsed")
        
        b1, b2 = st.columns([1, 1])
        with b1:
            if idx > 0:
                if st.button("⬅️ 上一题"): st.session_state.idx -= 1; st.rerun()
        with b2:
            if st.button("提交 ✅", type="primary"):
                if choice:
                    st.session_state.user_answers[idx] = choice
                    real_ans = current_q['ans'].strip().upper()
                    my_ans = choice.strip()[0].upper()
                    save_mistake_background(current_q['id'], my_ans, real_ans == my_ans)
                    st.rerun()
                else:
                    st.toast("请选择一项")
    else:
        # 解析区
        real_ans = current_q['ans'].strip().upper()
        my_ans_full = user_choice
        my_ans = my_ans_full.strip()[0].upper()
        is_correct = (real_ans == my_ans)

        # 自定义渲染选项
        for opt in current_q['opts']:
            opt_char = opt.strip()[0].upper()
            style = "opt-div"
            prefix = ""
            if opt_char == real_ans:
                style += " opt-correct"; prefix = "✅ "
            elif opt_char == my_ans and not is_correct:
                style += " opt-wrong"; prefix = "❌ "
            st.markdown(f"<div class='{style}'>{prefix}{opt}</div>", unsafe_allow_html=True)

        box_cls = "res-ok" if is_correct else "res-no"
        title = "回答正确！🎉" if is_correct else f"回答错误！正确答案：{real_ans}"
        
        st.markdown(f"""
        <div class='res-box {box_cls}'>
            <h4>{title}</h4>
            <hr style='opacity:0.2'>
            <p><b>🔍 解析：</b><br>{current_q['exp']}</p>
            <p style='margin-top:10px; font-size:14px; color:#666;'><b>🍬 技巧：</b>{current_q['guide']}</p>
        </div>
        """, unsafe_allow_html=True)

        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("⬅️ 上一题", key="p_done"): st.session_state.idx -= 1; st.rerun()
        with b2:
            if idx < total - 1:
                if st.button("下一题 ➡️", type="primary", key="n_done"): st.session_state.idx += 1; st.rerun()
            else:
                if st.button("完成练习 🏆", type="primary"):
                    sync_to_db()
                    clear_progress()
                    st.balloons()
                    st.success("完成！")
                    time.sleep(2)
                    st.session_state.page = "home"
                    st.rerun()
