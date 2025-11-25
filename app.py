import streamlit as st
import pymysql
import ssl
import time

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
# 🚀 极速连接核心 (针对手机端优化)
# ====================
@st.cache_resource
def get_db_connection():
    """建立一条永久连接通道，避免每次点击都重新排队"""
    try:
        return pymysql.connect(
            **TIDB_CONFIG,
            ssl={"check_hostname": False, "verify_mode": ssl.CERT_NONE},
            autocommit=True
        )
    except Exception as e:
        st.error(f"连接数据库失败，请检查网络。错误信息: {e}")
        return None

def get_conn():
    conn = get_db_connection()
    try:
        conn.ping(reconnect=True) # 保持心跳
    except:
        st.cache_resource.clear()
        conn = get_db_connection()
    return conn

# 缓存章节列表，避免重复查询
@st.cache_data(ttl=3600)
def get_categories():
    conn = get_conn()
    if not conn: return []
    with conn.cursor() as cursor:
        cursor.execute("SELECT category, COUNT(*) as c FROM question_bank GROUP BY category HAVING c > 0 ORDER BY c DESC")
        return [f"{r[0]} (共{r[1]}题)" for r in cursor.fetchall()]

# ====================
# ⚙️ 业务逻辑
# ====================
def init_mistake_book():
    try:
        conn = get_conn()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_record (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    question_id INT,
                    is_correct INT,
                    study_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_record (question_id) 
                );
            """)
    except: pass

def save_record(q_id, is_correct):
    try:
        conn = get_conn()
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO study_record (question_id, is_correct) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE is_correct = VALUES(is_correct), study_date = NOW()
            """
            cursor.execute(sql, (q_id, 1 if is_correct else 0))
    except: pass

def fetch_questions(mode, category_str=None, limit=10):
    conn = get_conn()
    if not conn: return []
    
    questions = []
    real_cat = category_str.split(" (")[0] if category_str else None
    
    sql = ""
    args = ()
    
    with conn.cursor() as cursor:
        if mode == "daily":
            # 每日一练：全库随机
            sql = "SELECT id, category, question, options, answer, explanation, beginner_guide FROM question_bank ORDER BY RAND() LIMIT %s"
            args = (limit,)
        elif mode == "chapter":
            # 章节：按分类随机
            sql = "SELECT id, category, question, options, answer, explanation, beginner_guide FROM question_bank WHERE category = %s ORDER BY RAND() LIMIT %s"
            args = (real_cat, limit)
        elif mode == "mistake":
            # 错题：只查做错的
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
            questions.append({
                "id": row[0],
                "category": row[1],
                "question": row[2],
                "options": eval(row[3]),
                "answer": row[4],
                "explanation": row[5],
                "guide": row[6] if row[6] else "暂无速记口诀"
            })
    return questions

# ====================
# 📱 页面 UI (V5.0 手机适配版)
# ====================
st.set_page_config(page_title="一消通关Pro", page_icon="🔥", layout="centered")

# 手机端 CSS 优化
st.markdown("""
<style>
    /* 按钮变大，方便手指点击 */
    .stButton>button { width: 100%; border-radius: 12px; height: 50px; font-size: 16px; margin-bottom: 10px; }
    /* 单选框间距优化 */
    .stRadio > div { background: #fff; padding: 12px; border-radius: 8px; border: 1px solid #eee; margin-bottom: 15px; }
    /* 解析框背景 */
    .explanation-box { background-color: #f0f7ff; padding: 15px; border-radius: 10px; border-left: 5px solid #007aff; margin-top: 10px; }
    /* 顶部导航隐藏 */
    header {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# 状态管理
if 'page' not in st.session_state: st.session_state.page = "home"
if 'answer_submitted' not in st.session_state: st.session_state.answer_submitted = False
if 'user_choice' not in st.session_state: st.session_state.user_choice = None

init_mistake_book()

# 🏠 首页
if st.session_state.page == "home":
    st.title("🔥 一消云题库")
    
    # 预加载章节
    cats = get_categories()

    # 两个大卡片按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅 每日一练\n(20题)", type="primary"):
            st.session_state.quiz_list = fetch_questions("daily", limit=20)
            st.session_state.current_index = 0
            st.session_state.score = 0
            st.session_state.answer_submitted = False
            st.session_state.page = "quiz"
            st.rerun()
    with col2:
        if st.button("📒 攻克错题\n(20题)"):
            q_list = fetch_questions("mistake", limit=20)
            if not q_list: st.toast("👍 错题本是空的！")
            else:
                st.session_state.quiz_list = q_list
                st.session_state.current_index = 0
                st.session_state.score = 0
                st.session_state.answer_submitted = False
                st.session_state.page = "quiz"
                st.rerun()

    st.markdown("### 📚 章节专项")
    if cats:
        selected_cat = st.selectbox("选择章节", cats, label_visibility="collapsed")
        if st.button(f"开始 {selected_cat.split(' (')[0]} 练习", type="secondary"):
            st.session_state.quiz_list = fetch_questions("chapter", category_str=selected_cat, limit=15)
            st.session_state.current_index = 0
            st.session_state.score = 0
            st.session_state.answer_submitted = False
            st.session_state.page = "quiz"
            st.rerun()
    else:
        st.info("正在从云端拉取数据，请稍后刷新...")

# 📝 做题页
elif st.session_state.page == "quiz":
    if not st.session_state.quiz_list:
        st.error("数据加载失败，请返回重试")
        if st.button("返回首页"):
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    total = len(st.session_state.quiz_list)
    idx = st.session_state.current_index

    # 结算页
    if idx >= total:
        st.balloons()
        st.success(f"🎉 练习完成！得分: {st.session_state.score}/{total}")
        if st.button("🏠 返回首页"):
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    q = st.session_state.quiz_list[idx]
    
    st.progress((idx + 1) / total)
    st.markdown(f"**{idx+1}. {q['question']}**")

    # 交互区域
    if not st.session_state.answer_submitted:
        choice = st.radio("选项", q['options'], index=None, key=f"radio_{idx}", label_visibility="collapsed")
        st.write("")
        if st.button("✅ 提交", type="primary"):
            if choice:
                st.session_state.user_choice = choice
                st.session_state.answer_submitted = True
                
                # 记录逻辑
                real = q['answer'].strip().upper()
                mine = choice[0].strip().upper()
                save_record(q['id'], real == mine)
                if real == mine: st.session_state.score += 1
                
                st.rerun()
            else:
                st.toast("⚠️ 请先选择一个答案")
    else:
        # 结果展示
        mine_str = st.session_state.user_choice
        real = q['answer'].strip().upper()
        mine = mine_str[0].strip().upper()
        
        if real == mine:
            st.success("✅ 回答正确")
        else:
            st.error(f"❌ 选了 {mine}，正确是 {real}")
            
        st.info(f"👉 你选的是：{mine_str}")

        # 解析
        st.markdown(f"""
        <div class="explanation-box">
            <b>💡 速记口诀：</b><br>{q['guide']}<br><br>
            <b>📖 官方解析：</b><br>{q['explanation']}
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        if st.button("➡️ 下一题", type="primary"):
            st.session_state.current_index += 1
            st.session_state.answer_submitted = False
            st.rerun()

    st.write("---")
    if st.button("🏠 退出"):
        st.session_state.page = "home"
        st.rerun()