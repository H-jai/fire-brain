import streamlit as st
import pymysql
import ssl
import time
import ast

# ==========================================
# ☁️ TiDB 数据库配置
# ==========================================
TIDB_CONFIG = {
    "host": "gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
    "port": 4000,
    "user": "2emKBRzbZrLBNax.root",
    "password": "Bh2VO3dlAEnhbv4G",
    "database": "test",
}

# ====================
# 🚀 数据库核心 (连接池)
# ====================
@st.cache_resource
def get_db_connection():
    """建立持久连接，减少握手时间"""
    try:
        return pymysql.connect(
            **TIDB_CONFIG,
            ssl={"check_hostname": False, "verify_mode": ssl.CERT_NONE},
            autocommit=True,
            connect_timeout=5
        )
    except:
        return None

def get_conn():
    conn = get_db_connection()
    try:
        conn.ping(reconnect=True)
    except:
        st.cache_resource.clear()
        conn = get_db_connection()
    return conn

# ====================
# 📥 数据存取逻辑
# ====================
def fetch_questions(mode, category_str=None, limit=20):
    """一次性拉取所有题目"""
    conn = get_conn()
    if not conn:
        st.error("网络连接失败，请检查网络")
        return []
    
    questions = []
    real_cat = category_str.split(" (")[0] if category_str else None
    
    try:
        with conn.cursor() as cursor:
            if mode == "daily":
                # 每日一练
                sql = "SELECT id, category, question, options, answer, explanation, beginner_guide FROM question_bank ORDER BY RAND() LIMIT %s"
                args = (limit,)
            elif mode == "chapter":
                # 章节练习
                sql = "SELECT id, category, question, options, answer, explanation, beginner_guide FROM question_bank WHERE category = %s ORDER BY RAND() LIMIT %s"
                args = (real_cat, limit)
            elif mode == "mistake":
                # 错题本
                sql = """
                    SELECT q.id, q.category, q.question, q.options, q.answer, q.explanation, q.beginner_guide 
                    FROM question_bank q
                    JOIN study_record s ON q.id = s.question_id
                    WHERE s.is_correct = 0
                    ORDER BY s.study_date DESC LIMIT %s
                """
                args = (limit,)
            
            cursor.execute(sql, args)
            rows = cursor.fetchall()
            
            for row in rows:
                # 安全解析选项
                try:
                    opts = ast.literal_eval(row[3])
                except:
                    opts = [str(row[3])]

                questions.append({
                    "id": row[0],
                    "category": row[1],
                    "question": row[2],
                    "options": opts,
                    "answer": row[4],
                    "explanation": row[5],
                    "guide": row[6] if row[6] else "暂无速记口诀"
                })
    except Exception as e:
        st.error(f"读取题目失败: {e}")
    
    return questions

def get_categories():
    conn = get_conn()
    if not conn: return []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT category, COUNT(*) as c FROM question_bank GROUP BY category HAVING c > 0 ORDER BY c DESC")
            return [f"{r[0]} (共{r[1]}题)" for r in cursor.fetchall()]
    except:
        return []

def batch_upload_records(records):
    """🚀 极速同步：最后一次性上传所有做题记录"""
    if not records: return
    conn = get_conn()
    if not conn: return
    
    try:
        with conn.cursor() as cursor:
            # 批量插入/更新 SQL
            sql = """
                INSERT INTO study_record (question_id, is_correct) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE is_correct = VALUES(is_correct), study_date = NOW()
            """
            cursor.executemany(sql, records)
            conn.commit()
    except Exception as e:
        print(f"上传失败: {e}")

# ====================
# 📱 页面 UI (极速版)
# ====================
st.set_page_config(page_title="一消极速版", page_icon="⚡", layout="centered")

# 针对手机端优化的 CSS
st.markdown("""
<style>
    /* 隐藏不需要的元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 按钮样式优化 */
    .stButton>button {
        width: 100%;
        height: 55px;
        border-radius: 12px;
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 15px;
        touch-action: manipulation; /* 防止双击缩放 */
    }
    
    /* 选项卡样式 */
    .stRadio > div {
        background: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #f0f0f0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    
    /* 解析框 */
    .exp-box {
        background-color: #f8fbff;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #007aff;
        margin-top: 20px;
        font-size: 15px;
    }
    
    /* 进度条颜色 */
    .stProgress > div > div > div > div {
        background-color: #007aff;
    }
</style>
""", unsafe_allow_html=True)

# 初始化 Session State
if 'page' not in st.session_state: st.session_state.page = "home"
if 'pending_upload' not in st.session_state: st.session_state.pending_upload = [] # 待上传的记录

# 🏠 首页
if st.session_state.page == "home":
    st.markdown("<h2 style='text-align: center; margin-bottom: 30px;'>⚡ 一消云题库 (极速版)</h2>", unsafe_allow_html=True)
    
    cats = get_categories()

    # 两个主入口
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅 每日一练", type="primary"):
            with st.spinner("正在下载题目..."):
                st.session_state.quiz_list = fetch_questions("daily", limit=15)
                if st.session_state.quiz_list:
                    st.session_state.current_index = 0
                    st.session_state.score = 0
                    st.session_state.answer_submitted = False
                    st.session_state.pending_upload = [] # 清空待上传
                    st.session_state.page = "quiz"
                    st.rerun()
    
    with col2:
        if st.button("📒 攻克错题"):
            with st.spinner("正在查找错题..."):
                q_list = fetch_questions("mistake", limit=15)
                if not q_list:
                    st.toast("🎉 没有错题，太棒了！")
                else:
                    st.session_state.quiz_list = q_list
                    st.session_state.current_index = 0
                    st.session_state.score = 0
                    st.session_state.answer_submitted = False
                    st.session_state.pending_upload = []
                    st.session_state.page = "quiz"
                    st.rerun()

    st.markdown("### 📚 章节练习")
    if cats:
        sel_cat = st.selectbox("选择章节", cats, label_visibility="collapsed")
        if st.button("开始练习", type="secondary"):
            with st.spinner("准备中..."):
                st.session_state.quiz_list = fetch_questions("chapter", category_str=sel_cat, limit=15)
                st.session_state.current_index = 0
                st.session_state.score = 0
                st.session_state.answer_submitted = False
                st.session_state.pending_upload = []
                st.session_state.page = "quiz"
                st.rerun()
    else:
        st.info("正在连接云端，请稍候...")

# 📝 做题页 (纯本地交互，无网络延迟)
elif st.session_state.page == "quiz":
    q_list = st.session_state.quiz_list
    total = len(q_list)
    idx = st.session_state.current_index

    # --- 结算逻辑 ---
    if idx >= total:
        st.balloons()
        # 此时才上传数据
        if st.session_state.pending_upload:
            with st.spinner("正在保存学习记录..."):
                batch_upload_records(st.session_state.pending_upload)
        
        st.success(f"本次练习结束！得分: {st.session_state.score} / {total}")
        
        if st.button("🏠 返回首页"):
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    # --- 题目显示 ---
    q = q_list[idx]
    
    # 顶部进度和退出
    c1, c2 = st.columns([3, 1])
    with c1:
        st.progress((idx) / total)
    with c2:
        if st.button("退出", key="exit_btn"):
            # 中途退出也要保存
            if st.session_state.pending_upload:
                batch_upload_records(st.session_state.pending_upload)
            st.session_state.page = "home"
            st.rerun()

    st.markdown(f"**第 {idx+1}/{total} 题：**")
    st.markdown(f"#### {q['question']}")

    # --- 交互区 ---
    if not st.session_state.answer_submitted:
        # 选项
        choice = st.radio("请选择:", q['options'], index=None, key=f"q_{idx}_{q['id']}")
        
        st.write("") # 占位
        if st.button("提交答案", type="primary"):
            if choice:
                st.session_state.user_choice = choice
                st.session_state.answer_submitted = True
                
                # 判分 (纯内存操作，极速)
                real = str(q['answer']).strip().upper()
                mine = str(choice)[0].strip().upper()
                is_right = (real == mine)
                
                if is_right: st.session_state.score += 1
                
                # 放入待传列表，暂不上传
                st.session_state.pending_upload.append((q['id'], 1 if is_right else 0))
                st.rerun()
            else:
                st.toast("请先选择一个选项")
    else:
        # --- 结果解析区 ---
        choice = st.session_state.user_choice
        real = str(q['answer']).strip().upper()
        mine = str(choice)[0].strip().upper()
        
        if real == mine:
            st.success("✅ 回答正确")
        else:
            st.error(f"❌ 选了 {mine}，正确是 {real}")
            
        st.markdown(f"""
        <div class="exp-box">
            <b>💡 记忆口诀：</b><br>{q['guide']}<br><br>
            <b>📖 详细解析：</b><br>{q['explanation']}
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        # 这个按钮现在也是秒开，因为不读数据库
        if st.button("下一题 ➡️", type="primary"):
            st.session_state.current_index += 1
            st.session_state.answer_submitted = False
            st.rerun()