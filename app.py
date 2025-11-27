import streamlit as st
import pymysql
import ssl
import ast
import time
import json
from datetime import datetime

# TiDB 配置
TIDB_CONFIG = {
    "host": "gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
    "port": 4000,
    "user": "2emKBRzbZrLBNax.root",
    "password": "Bh2VO3dlAEnhbv4G",
    "database": "test",
}

# --- 数据库连接 ---
@st.cache_resource
def get_db_connection():
    try:
        return pymysql.connect(
            **TIDB_CONFIG,
            ssl={"check_hostname": False, "verify_mode": ssl.CERT_NONE},
            autocommit=True,
            connect_timeout=10
        )
    except: return None

def get_conn():
    conn = get_db_connection()
    try: conn.ping(reconnect=True)
    except: 
        st.cache_resource.clear()
        conn = get_db_connection()
    return conn

# --- 初始化表结构 (自动创建) ---
def init_tables():
    conn = get_conn()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            # 答题记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_record (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    question_id INT,
                    user_answer VARCHAR(10),
                    is_correct TINYINT,
                    study_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX(question_id, is_correct)
                )
            """)
            # 进度保存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_type VARCHAR(50),
                    current_index INT DEFAULT 0,
                    score INT DEFAULT 0,
                    elapsed_time INT DEFAULT 0,
                    question_ids TEXT,
                    last_update DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY(source_type)
                )
            """)
    except Exception as e:
        st.error(f"表初始化失败: {e}")

# --- 保存进度到云端 ---
def save_progress(source_type, idx, score, elapsed, q_ids):
    conn = get_conn()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO study_progress (source_type, current_index, score, elapsed_time, question_ids)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    current_index=%s, score=%s, elapsed_time=%s, question_ids=%s
            """, (source_type, idx, score, elapsed, json.dumps(q_ids), idx, score, elapsed, json.dumps(q_ids)))
    except: pass

# --- 加载进度 ---
def load_progress(source_type):
    conn = get_conn()
    if not conn: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT current_index, score, elapsed_time, question_ids FROM study_progress WHERE source_type=%s", (source_type,))
            row = cursor.fetchone()
            if row:
                return {
                    "idx": row[0],
                    "score": row[1],
                    "elapsed": row[2],
                    "q_ids": json.loads(row[3])
                }
    except: pass
    return None

# --- 删除进度 ---
def clear_progress(source_type):
    conn = get_conn()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM study_progress WHERE source_type=%s", (source_type,))
    except: pass

# --- 保存答题记录 ---
def save_answer_record(q_id, user_ans, is_correct):
    conn = get_conn()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO study_record (question_id, user_answer, is_correct) VALUES (%s, %s, %s)",
                (q_id, user_ans, 1 if is_correct else 0)
            )
    except: pass

# --- 获取题目 ---
def fetch_questions(source_type, limit=100):
    conn = get_conn()
    if not conn: return []
    questions = []
    try:
        with conn.cursor() as cursor:
            if source_type == "mistake":
                # 错题本：只取做错的题
                sql = """
                    SELECT DISTINCT q.id, q.question, q.options, q.answer, q.explanation, q.beginner_guide, q.source_type 
                    FROM question_bank q 
                    JOIN study_record s ON q.id=s.question_id 
                    WHERE s.is_correct=0 
                    ORDER BY s.study_date DESC 
                    LIMIT %s
                """
                args = (limit,)
            else:
                # 普通题库：随机抽取，但优先取数量少的
                sql = """
                    SELECT id, question, options, answer, explanation, beginner_guide, source_type 
                    FROM question_bank 
                    WHERE source_type=%s 
                    ORDER BY RAND() 
                    LIMIT %s
                """
                args = (source_type, limit)
            
            cursor.execute(sql, args)
            for row in cursor.fetchall():
                try: opts = ast.literal_eval(row[2])
                except: opts = [str(row[2])]
                questions.append({
                    "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                    "exp": row[4], "guide": row[5], "type": row[6]
                })
    except Exception as e:
        st.error(f"题目加载失败: {e}")
    return questions

# --- 获取统计数据 ---
def get_stats():
    conn = get_conn()
    stats = {"历年真题":0, "普通资料":0, "加强记忆":0, "错题":0}
    if not conn: return stats
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT source_type, COUNT(*) FROM question_bank GROUP BY source_type")
            for r in cursor.fetchall():
                if r[0] in stats: stats[r[0]] = r[1]
            # 错题数量
            cursor.execute("SELECT COUNT(DISTINCT question_id) FROM study_record WHERE is_correct=0")
            stats["错题"] = cursor.fetchone()[0]
    except: pass
    return stats

# --- 页面设置 ---
st.set_page_config(page_title="消防大脑", page_icon="🔥", layout="centered")

st.markdown("""
<style>
    .stButton>button { 
        width: 100%; height: 50px; border-radius: 10px; font-weight: bold; 
        transition: all 0.3s;
    }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    
    .result-box { 
        padding: 15px; border-radius: 8px; margin-top: 10px; 
        animation: slideIn 0.4s ease-out;
    }
    .result-correct { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); border: 2px solid #10b981; }
    .result-wrong { background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); border: 2px solid #ef4444; }
    
    .opt-box { 
        padding: 12px; margin: 8px 0; border: 2px solid #e5e7eb; 
        border-radius: 8px; background: white; cursor: pointer;
        transition: all 0.2s;
    }
    .opt-box:hover { border-color: #3b82f6; transform: translateX(5px); }
    .opt-correct { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); border-color: #10b981; font-weight: bold; }
    .opt-wrong { background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); border-color: #ef4444; opacity: 0.7; }
    
    .timer { 
        font-size: 24px; font-weight: bold; color: #1f2937;
        text-align: center; padding: 10px;
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        border-radius: 8px; margin-bottom: 10px;
    }
    
    @keyframes slideIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    
    #MainMenu, footer, header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 初始化 ---
init_tables()

if 'page' not in st.session_state: st.session_state.page = "home"
if 'q_list' not in st.session_state: st.session_state.q_list = []
if 'idx' not in st.session_state: st.session_state.idx = 0
if 'score' not in st.session_state: st.session_state.score = 0
if 'submitted' not in st.session_state: st.session_state.submitted = False
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'elapsed_time' not in st.session_state: st.session_state.elapsed_time = 0
if 'paused' not in st.session_state: st.session_state.paused = False
if 'pause_start' not in st.session_state: st.session_state.pause_start = None
if 'source_type' not in st.session_state: st.session_state.source_type = ""

# 🏠 首页
if st.session_state.page == "home":
    st.title("🔥 消防大脑 V7.0")
    st.caption("支持进度保存 · 计时训练 · 错题追踪")
    
    stats = get_stats()

    # 检查是否有未完成的进度
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"📚 普通资料 ({stats['普通资料']}题)")
        progress = load_progress("普通资料")
        if progress and progress['idx'] < len(progress['q_ids']):
            st.warning(f"🔄 有未完成进度 ({progress['idx']}/{len(progress['q_ids'])}题)")
            if st.button("继续练习", key="continue_normal"):
                st.session_state.source_type = "普通资料"
                st.session_state.page = "quiz"
                st.session_state.idx = progress['idx']
                st.session_state.score = progress['score']
                st.session_state.elapsed_time = progress['elapsed']
                # 根据保存的 ID 重新加载题目
                conn = get_conn()
                if conn:
                    with conn.cursor() as cursor:
                        ids_str = ','.join(map(str, progress['q_ids']))
                        cursor.execute(f"SELECT id, question, options, answer, explanation, beginner_guide, source_type FROM question_bank WHERE id IN ({ids_str})")
                        st.session_state.q_list = []
                        for row in cursor.fetchall():
                            try: opts = ast.literal_eval(row[2])
                            except: opts = [str(row[2])]
                            st.session_state.q_list.append({
                                "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                                "exp": row[4], "guide": row[5], "type": row[6]
                            })
                st.rerun()
        
        if st.button("🆕 开始新练习", key="btn_normal"):
            clear_progress("普通资料")
            st.session_state.q_list = fetch_questions("普通资料", 100)
            st.session_state.source_type = "普通资料"
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.score = 0
            st.session_state.elapsed_time = 0
            st.session_state.start_time = time.time()
            st.rerun()
            
    with col2:
        st.error(f"💯 历年真题 ({stats['历年真题']}题)")
        progress = load_progress("历年真题")
        if progress and progress['idx'] < len(progress['q_ids']):
            st.warning(f"🔄 有未完成进度 ({progress['idx']}/{len(progress['q_ids'])}题)")
            if st.button("继续练习", key="continue_real"):
                st.session_state.source_type = "历年真题"
                st.session_state.page = "quiz"
                st.session_state.idx = progress['idx']
                st.session_state.score = progress['score']
                st.session_state.elapsed_time = progress['elapsed']
                conn = get_conn()
                if conn:
                    with conn.cursor() as cursor:
                        ids_str = ','.join(map(str, progress['q_ids']))
                        cursor.execute(f"SELECT id, question, options, answer, explanation, beginner_guide, source_type FROM question_bank WHERE id IN ({ids_str})")
                        st.session_state.q_list = []
                        for row in cursor.fetchall():
                            try: opts = ast.literal_eval(row[2])
                            except: opts = [str(row[2])]
                            st.session_state.q_list.append({
                                "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                                "exp": row[4], "guide": row[5], "type": row[6]
                            })
                st.rerun()
        
        if st.button("🆕 全真模拟", key="btn_real"):
            clear_progress("历年真题")
            st.session_state.q_list = fetch_questions("历年真题", 100)
            st.session_state.source_type = "历年真题"
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.score = 0
            st.session_state.elapsed_time = 0
            st.session_state.start_time = time.time()
            st.rerun()

    st.warning(f"🧠 加强记忆 ({stats['加强记忆']}题)")
    progress = load_progress("加强记忆")
    if progress and progress['idx'] < len(progress['q_ids']):
        st.info(f"🔄 有未完成进度 ({progress['idx']}/{len(progress['q_ids'])}题)")
        if st.button("继续背诵", key="continue_memory"):
            st.session_state.source_type = "加强记忆"
            st.session_state.page = "quiz"
            st.session_state.idx = progress['idx']
            st.session_state.score = progress['score']
            st.session_state.elapsed_time = progress['elapsed']
            conn = get_conn()
            if conn:
                with conn.cursor() as cursor:
                    ids_str = ','.join(map(str, progress['q_ids']))
                    cursor.execute(f"SELECT id, question, options, answer, explanation, beginner_guide, source_type FROM question_bank WHERE id IN ({ids_str})")
                    st.session_state.q_list = []
                    for row in cursor.fetchall():
                        try: opts = ast.literal_eval(row[2])
                        except: opts = [str(row[2])]
                        st.session_state.q_list.append({
                            "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                            "exp": row[4], "guide": row[5], "type": row[6]
                        })
            st.rerun()
    
    if st.button("🆕 开始背诵", key="btn_memory"):
        clear_progress("加强记忆")
        st.session_state.q_list = fetch_questions("加强记忆", 100)
        st.session_state.source_type = "加强记忆"
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.score = 0
        st.session_state.elapsed_time = 0
        st.session_state.start_time = time.time()
        st.rerun()

    if st.button(f"📒 攻克错题本 ({stats['错题']}题)", type="secondary"):
        st.session_state.q_list = fetch_questions("mistake", 100)
        st.session_state.source_type = "错题本"
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.score = 0
        st.session_state.elapsed_time = 0
        st.session_state.start_time = time.time()
        st.rerun()

# 📝 做题页
elif st.session_state.page == "quiz":
    if not st.session_state.q_list:
        st.warning("⚠️ 题库中暂时没有这类题目，请先上传！")
        if st.button("返回"): 
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    q_data = st.session_state.q_list
    idx = st.session_state.idx
    total = len(q_data)

    # 计算实时用时
    if st.session_state.start_time and not st.session_state.paused:
        current_elapsed = st.session_state.elapsed_time + int(time.time() - st.session_state.start_time)
    else:
        current_elapsed = st.session_state.elapsed_time
    
    mins = current_elapsed // 60
    secs = current_elapsed % 60

    # 完成页面
    if idx >= total:
        st.balloons()
        st.success(f"🎉 练习结束！")
        st.metric("得分", f"{st.session_state.score}/{total}", f"{int(st.session_state.score/total*100)}%")
        st.metric("用时", f"{mins}分{secs}秒")
        
        # 清除进度
        clear_progress(st.session_state.source_type)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🏠 返回首页", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
        with col2:
            if st.button("🔄 再练一次", use_container_width=True):
                st.session_state.idx = 0
                st.session_state.score = 0
                st.session_state.elapsed_time = 0
                st.session_state.start_time = time.time()
                st.session_state.submitted = False
                st.rerun()
        st.stop()

    q = q_data[idx]
    
    # 顶部控制栏
    col1, col2, col3 = st.columns([2,3,2])
    with col1:
        if st.button("🏠 返回", use_container_width=True):
            # 保存进度
            q_ids = [item['id'] for item in q_data]
            save_progress(st.session_state.source_type, idx, st.session_state.score, current_elapsed, q_ids)
            st.session_state.page = "home"
            st.rerun()
    
    with col2:
        st.markdown(f'<div class="timer">⏱️ {mins:02d}:{secs:02d}</div>', unsafe_allow_html=True)
    
    with col3:
        if not st.session_state.paused:
            if st.button("⏸️ 暂停", use_container_width=True):
                st.session_state.paused = True
                st.session_state.pause_start = time.time()
                # 累计已用时间
                st.session_state.elapsed_time = current_elapsed
                st.rerun()
        else:
            if st.button("▶️ 继续", use_container_width=True):
                st.session_state.paused = False
                st.session_state.start_time = time.time()
                st.rerun()
    
    # 暂停遮罩
    if st.session_state.paused:
        st.info("⏸️ 已暂停，点击「继续」恢复答题")
        st.stop()

    # 进度条
    st.progress((idx+1)/total)
    st.caption(f"第 {idx+1}/{total} 题 • {q['type']}")
    st.markdown(f"### {q['q']}")

    # 未提交状态
    if not st.session_state.submitted:
        choice = st.radio("请选择:", q['opts'], index=None, key=f"q_{idx}", label_visibility="collapsed")
        
        col1, col2, col3 = st.columns([1,2,1])
        with col1:
            if idx > 0:
                if st.button("⬅️ 上一题", use_container_width=True):
                    st.session_state.idx -= 1
                    st.session_state.submitted = False
                    st.rerun()
        
        with col2:
            if st.button("✅ 提交答案", type="primary", use_container_width=True):
                if choice:
                    st.session_state.user_choice = choice
                    st.session_state.submitted = True
                    
                    real_ans = q['ans'].strip().upper()
                    my_ans = choice[0].strip().upper()
                    is_correct = (real_ans == my_ans)
                    
                    if is_correct: 
                        st.session_state.score += 1
                    
                    # 保存答题记录
                    save_answer_record(q['id'], my_ans, is_correct)
                    
                    st.rerun()
                else:
                    st.toast("⚠️ 请选择一项")
        
        with col3:
            pass  # 占位
    
    # 已提交状态
    else:
        real_ans = q['ans'].strip().upper()
        my_ans = st.session_state.user_choice[0].strip().upper()
        
        # 显示选项
        for opt in q['opts']:
            opt_char = opt[0].strip().upper()
            
            if opt_char == real_ans:
                st.markdown(f'<div class="opt-box opt-correct">✅ {opt}</div>', unsafe_allow_html=True)
            elif opt_char == my_ans and my_ans != real_ans:
                st.markdown(f'<div class="opt-box opt-wrong">❌ {opt}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="opt-box">{opt}</div>', unsafe_allow_html=True)

        # 结果面板
        is_correct = (my_ans == real_ans)
        box_class = "result-correct" if is_correct else "result-wrong"
        msg = "🎉 回答正确！" if is_correct else f"❌ 回答错误！正确答案是 {real_ans}"
        
        st.markdown(f"""
        <div class="result-box {box_class}">
            <h4>{msg}</h4>
            <hr style="margin:10px 0; border:none; border-top:1px solid rgba(0,0,0,0.1);">
            <b>💡 记忆口诀：</b>{q['guide']}<br><br>
            <b>📖 详细解析：</b><br>{q['exp']}
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        
        col1, col2 = st.columns([1,1])
        with col1:
            if idx > 0:
                if st.button("⬅️ 上一题", use_container_width=True):
                    st.session_state.idx -= 1
                    st.session_state.submitted = False
                    st.rerun()
        
        with col2:
            if st.button("➡️ 下一题", type="primary", use_container_width=True):
                st.session_state.idx += 1
                st.session_state.submitted = False
                
                # 保存进度到云端
                q_ids = [item['id'] for item in q_data]
                save_progress(st.session_state.source_type, st.session_state.idx, st.session_state.score, current_elapsed, q_ids)
                
                st.rerun()