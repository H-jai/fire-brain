import streamlit as st
import pymysql
import ssl
import ast
import time
from datetime import datetime

# =========================================================================
# 👇 配置区
# =========================================================================
TIDB_CONFIG = {
    "host": "gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
    "port": 4000,
    "user": "2emKBRzbZrLBNax.root",
    "password": "Bh2VO3dlAEnhbv4G",
    "database": "test",
}

# =========================================================================
# 👇 核心逻辑：数据库连接与缓存
# =========================================================================

@st.cache_resource
def get_db_pool():
    """连接池：只连接一次，避免反复握手导致卡顿"""
    try:
        return pymysql.connect(
            **TIDB_CONFIG,
            ssl={"check_hostname": False, "verify_mode": ssl.CERT_NONE},
            autocommit=True,
            connect_timeout=3
        )
    except:
        return None

def save_record_background(q_id, user_ans, is_correct):
    """后台保存做题记录，不阻塞界面"""
    if 'unsaved_records' not in st.session_state:
        st.session_state.unsaved_records = []
    
    # 暂存到内存
    st.session_state.unsaved_records.append({
        "qid": q_id, "ans": user_ans, "ok": 1 if is_correct else 0, "time": datetime.now()
    })
    
    # 凑够3条或者做错题时，批量写库（避免频繁联网）
    if len(st.session_state.unsaved_records) >= 3 or not is_correct:
        sync_to_db()

def sync_to_db():
    """将暂存的记录真正写入数据库"""
    records = st.session_state.get('unsaved_records', [])
    if not records: return
    
    conn = get_db_pool()
    if conn:
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as c:
                sql = "INSERT INTO study_record (question_id, user_answer, is_correct, study_date) VALUES (%s, %s, %s, %s)"
                data = [(r['qid'], r['ans'], r['ok'], r['time']) for r in records]
                c.executemany(sql, data)
            st.session_state.unsaved_records = [] # 清空
        except Exception as e:
            print(f"Sync error: {e}")

@st.cache_data(ttl=600)
def fetch_questions(source_type, limit=50):
    """一次性拉取50道题，本地缓存，做题时无需再联网"""
    conn = get_db_pool()
    if not conn: return []
    
    questions = []
    try:
        conn.ping(reconnect=True)
        with conn.cursor() as c:
            if source_type == "mistake":
                # 错题本逻辑
                sql = """SELECT DISTINCT q.id, q.question, q.options, q.answer, q.explanation, q.beginner_guide 
                         FROM question_bank q JOIN study_record s ON q.id=s.question_id 
                         WHERE s.is_correct=0 ORDER BY s.study_date DESC LIMIT %s"""
                c.execute(sql, (limit,))
            else:
                # 随机出题
                sql = """SELECT id, question, options, answer, explanation, beginner_guide 
                         FROM question_bank WHERE source_type=%s ORDER BY RAND() LIMIT %s"""
                c.execute(sql, (source_type, limit))
            
            for row in c.fetchall():
                # 容错处理：解析选项格式
                raw_opt = row[2]
                try:
                    opts = ast.literal_eval(raw_opt)
                    if not isinstance(opts, list): opts = [str(raw_opt)]
                except:
                    opts = [str(raw_opt)]
                
                questions.append({
                    "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                    "exp": row[4], "guide": row[5]
                })
    except: pass
    return questions

# =========================================================================
# 👇 界面 UI 样式
# =========================================================================
st.set_page_config(page_title="消防刷题Pro", page_icon="🔥", layout="mobile")

st.markdown("""
<style>
    /* 顶部导航栏模拟 */
    .top-bar {
        display: flex; justify-content: space-between; align-items: center;
        background: #fff; padding: 10px; border-radius: 10px; border: 1px solid #eee;
        margin-bottom: 15px;
    }
    .timer-box { font-weight: bold; font-size: 18px; color: #333; }
    
    /* 按钮美化 */
    .stButton>button { border-radius: 20px; font-weight: bold; }
    
    /* 结果框 */
    .res-box { padding: 15px; border-radius: 10px; margin-top: 10px; animation: fadeIn 0.5s; }
    .res-ok { background: #d1fae5; border: 1px solid #34d399; color: #064e3b; }
    .res-no { background: #fee2e2; border: 1px solid #f87171; color: #7f1d1d; }
    
    /* 选项 */
    .opt-div { padding: 10px; margin: 5px 0; border: 1px solid #e5e7eb; border-radius: 8px; }
    .opt-sel { border: 2px solid #3b82f6; background: #eff6ff; }
    .opt-correct { background: #dcfce7; border-color: #22c55e; }
    .opt-wrong { background: #fee2e2; border-color: #ef4444; }
    
    @keyframes fadeIn { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:translateY(0); } }
</style>
""", unsafe_allow_html=True)

# =========================================================================
# 👇 状态管理
# =========================================================================
if 'page' not in st.session_state: st.session_state.page = "home"
if 'q_list' not in st.session_state: st.session_state.q_list = []
if 'idx' not in st.session_state: st.session_state.idx = 0
if 'user_answers' not in st.session_state: st.session_state.user_answers = {} # 记录每一题的答案 {idx: choice}
if 'start_time' not in st.session_state: st.session_state.start_time = None

# =========================================================================
# 👇 首页
# =========================================================================
if st.session_state.page == "home":
    st.title("🔥 消防大脑")
    st.caption("智能考点分析 | 场景化出题")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📚 普通资料\n(50题)", use_container_width=True):
            st.session_state.q_list = fetch_questions("普通资料", 50)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.user_answers = {}
            st.session_state.start_time = time.time()
            st.rerun()
    with col2:
        if st.button("💯 历年真题\n(50题)", use_container_width=True):
            st.session_state.q_list = fetch_questions("历年真题", 50)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.user_answers = {}
            st.session_state.start_time = time.time()
            st.rerun()

    if st.button("📒 错题本 (复习错题)", use_container_width=True):
        st.session_state.q_list = fetch_questions("mistake", 30)
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.user_answers = {}
        st.session_state.start_time = time.time()
        st.rerun()

# =========================================================================
# 👇 做题界面
# =========================================================================
elif st.session_state.page == "quiz":
    if not st.session_state.q_list:
        st.warning("暂无题目，请先上传资料！")
        if st.button("返回"): st.session_state.page = "home"; st.rerun()
        st.stop()

    # 1. 顶部控制栏 (仿截图)
    # 计算时间
    seconds = int(time.time() - st.session_state.start_time)
    time_str = f"{seconds//60:02d}:{seconds%60:02d}"
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("🏠 返回"):
            sync_to_db() # 退出前保存
            st.session_state.page = "home"
            st.rerun()
    with c2:
        st.markdown(f"<div style='text-align:center; font-size:20px; font-weight:bold;'>⏱️ {time_str}</div>", unsafe_allow_html=True)
    with c3:
        if st.button("⏸ 暂停"):
            st.toast("已暂停 (功能开发中)")

    # 2. 进度条
    q_data = st.session_state.q_list
    total = len(q_data)
    idx = st.session_state.idx
    current_q = q_data[idx]
    
    st.progress((idx + 1) / total)
    st.caption(f"第 {idx + 1} / {total} 题")

    # 3. 题目显示
    st.markdown(f"### {current_q['q']}")

    # 4. 选项与交互逻辑
    # 检查这道题是否已经做过
    has_answered = idx in st.session_state.user_answers
    user_choice = st.session_state.user_answers.get(idx)

    if not has_answered:
        # --- 未做答模式 ---
        choice = st.radio("请选择:", current_q['opts'], index=None, key=f"radio_{idx}", label_visibility="collapsed")
        
        # 底部按钮区
        b1, b2 = st.columns([1, 1])
        with b1:
            # 上一题按钮 (如果是第一题则禁用)
            if idx > 0:
                if st.button("⬅️ 上一题"):
                    st.session_state.idx -= 1
                    st.rerun()
            else:
                st.button("⬅️ 上一题", disabled=True)
        
        with b2:
            if st.button("提交答案 ✅", type="primary"):
                if choice:
                    st.session_state.user_answers[idx] = choice # 记录答案
                    
                    # 判断对错并后台保存
                    real_ans = current_q['ans'].strip().upper()
                    my_ans = choice[0].strip().upper()
                    is_correct = (real_ans == my_ans)
                    save_record_background(current_q['id'], my_ans, is_correct)
                    
                    st.rerun() # 刷新以显示结果
                else:
                    st.toast("请先选择一个选项")
    
    else:
        # --- 已做答模式 (显示解析) ---
        real_ans = current_q['ans'].strip().upper()
        my_ans = user_choice[0].strip().upper()
        is_correct = (real_ans == my_ans)

        # 渲染彩色选项
        for opt in current_q['opts']:
            opt_char = opt[0].strip().upper()
            style = "opt-div"
            if opt_char == real_ans:
                style += " opt-correct" # 绿色正确
                opt = "✅ " + opt
            elif opt_char == my_ans and not is_correct:
                style += " opt-wrong"   # 红色错误
                opt = "❌ " + opt
            elif opt_char == my_ans:
                style += " opt-correct" # 选对了
            
            st.markdown(f"<div class='{style}'>{opt}</div>", unsafe_allow_html=True)

        # 结果解析框
        box_cls = "res-ok" if is_correct else "res-no"
        title = "回答正确！🎉" if is_correct else f"回答错误！正确答案：{real_ans}"
        
        st.markdown(f"""
        <div class='res-box {box_cls}'>
            <h4>{title}</h4>
            <hr style='opacity:0.2'>
            <p><b>🔑 口诀：</b>{current_q['guide']}</p>
            <p><b>📖 解析：</b>{current_q['exp']}</p>
        </div>
        """, unsafe_allow_html=True)

        # 底部导航
        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("⬅️ 上一题", key="prev_done"):
                st.session_state.idx -= 1
                st.rerun()
        with b2:
            if idx < total - 1:
                if st.button("下一题 ➡️", type="primary", key="next_done"):
                    st.session_state.idx += 1
                    st.rerun()
            else:
                if st.button("完成练习 🏆", type="primary"):
                    sync_to_db()
                    st.balloons()
                    st.success("练习结束！")
                    time.sleep(2)
                    st.session_state.page = "home"
                    st.rerun()
