import streamlit as st
import pymysql
import ssl
import ast
import random

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
            connect_timeout=5
        )
    except: return None

def get_conn():
    conn = get_db_connection()
    try: conn.ping(reconnect=True)
    except: 
        st.cache_resource.clear()
        conn = get_db_connection()
    return conn

# --- 获取题目 (支持 source_type 分类) ---
def fetch_questions(source_type, limit=20):
    conn = get_conn()
    if not conn: return []
    questions = []
    try:
        with conn.cursor() as cursor:
            # 根据类型筛选
            if source_type == "mistake":
                sql = """SELECT q.id, q.question, q.options, q.answer, q.explanation, q.beginner_guide, q.source_type 
                         FROM question_bank q JOIN study_record s ON q.id=s.question_id 
                         WHERE s.is_correct=0 ORDER BY s.study_date DESC LIMIT %s"""
                args = (limit,)
            else:
                sql = "SELECT id, question, options, answer, explanation, beginner_guide, source_type FROM question_bank WHERE source_type=%s ORDER BY RAND() LIMIT %s"
                args = (source_type, limit)
            
            cursor.execute(sql, args)
            for row in cursor.fetchall():
                try: opts = ast.literal_eval(row[2])
                except: opts = [str(row[2])]
                questions.append({
                    "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                    "exp": row[4], "guide": row[5], "type": row[6]
                })
    except: pass
    return questions

def get_stats():
    conn = get_conn()
    stats = {"历年真题":0, "普通资料":0, "加强记忆":0}
    if not conn: return stats
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT source_type, COUNT(*) FROM question_bank GROUP BY source_type")
            for r in cursor.fetchall():
                if r[0] in stats: stats[r[0]] = r[1]
    except: pass
    return stats

# --- 页面设置 ---
st.set_page_config(page_title="消防大脑", page_icon="🔥", layout="centered")

st.markdown("""
<style>
    /* 全局按钮 */
    .stButton>button { width: 100%; height: 50px; border-radius: 10px; font-weight: bold; }
    
    /* 结果面板 */
    .result-box { padding: 15px; border-radius: 8px; margin-top: 10px; animation: fadeIn 0.5s; }
    .result-correct { background-color: #d1fae5; border: 1px solid #10b981; color: #065f46; }
    .result-wrong { background-color: #fee2e2; border: 1px solid #ef4444; color: #991b1b; }
    
    /* 选项展示 */
    .opt-box { padding: 10px; margin: 5px 0; border: 1px solid #eee; border-radius: 8px; background: #fff; }
    .opt-correct { background-color: #d1fae5; border-color: #10b981; font-weight: bold; }
    .opt-wrong { background-color: #fee2e2; border-color: #ef4444; text-decoration: line-through; color: #888; }
    .opt-neutral { color: #333; }
    
    /* 隐藏默认元素 */
    #MainMenu, footer, header {visibility: hidden;}
    
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
""", unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = "home"
if 'q_list' not in st.session_state: st.session_state.q_list = []
if 'idx' not in st.session_state: st.session_state.idx = 0
if 'score' not in st.session_state: st.session_state.score = 0
if 'submitted' not in st.session_state: st.session_state.submitted = False

# 🏠 首页
if st.session_state.page == "home":
    st.title("🔥 消防大脑 (V6)")
    stats = get_stats()

    # 三大板块入口
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"📚 普通资料\n({stats['普通资料']}题)")
        if st.button("开始练习", key="btn_normal"):
            st.session_state.q_list = fetch_questions("普通资料", 20)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.score = 0
            st.rerun()
            
    with col2:
        st.error(f"💯 历年真题\n({stats['历年真题']}题)")
        if st.button("全真模拟", key="btn_real"):
            st.session_state.q_list = fetch_questions("历年真题", 20)
            st.session_state.page = "quiz"
            st.session_state.idx = 0
            st.session_state.score = 0
            st.rerun()

    st.warning(f"🧠 加强记忆 ({stats['加强记忆']}题)")
    if st.button("进入背诵模式", key="btn_memory"):
        st.session_state.q_list = fetch_questions("加强记忆", 20)
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.score = 0
        st.rerun()

    if st.button("📒 攻克错题本", type="secondary"):
        st.session_state.q_list = fetch_questions("mistake", 20)
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.score = 0
        st.rerun()

# 📝 做题页 (UI 重构版)
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

    if idx >= total:
        st.success(f"🎉 练习结束！得分: {st.session_state.score}/{total}")
        if st.button("返回首页"):
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    q = q_data[idx]
    
    # 顶部进度
    st.progress((idx+1)/total)
    st.caption(f"第 {idx+1}/{total} 题 • {q['type']}")
    st.markdown(f"### {q['q']}")

    # --- 核心 UI 逻辑 ---
    
    # 如果没提交，显示单选框
    if not st.session_state.submitted:
        choice = st.radio("请选择:", q['opts'], index=None, key=f"q_{idx}", label_visibility="collapsed")
        st.write("")
        if st.button("提交答案", type="primary"):
            if choice:
                st.session_state.user_choice = choice
                st.session_state.submitted = True
                real_ans = q['ans'].strip().upper()
                my_ans = choice[0].strip().upper()
                if real_ans == my_ans: st.session_state.score += 1
                st.rerun()
            else:
                st.toast("请选择一项")
    
    # 如果已提交，显示静态对比界面 (这就是你要的效果！)
    else:
        real_ans = q['ans'].strip().upper()
        my_ans = st.session_state.user_choice[0].strip().upper()
        
        # 1. 静态显示所有选项，标记颜色
        for opt in q['opts']:
            opt_char = opt[0].strip().upper()
            style_class = "opt-neutral"
            
            # 逻辑：如果是正确答案 -> 绿；如果是选错的 -> 红
            if opt_char == real_ans:
                style_class = "opt-correct"
                icon = "✅"
            elif opt_char == my_ans and my_ans != real_ans:
                style_class = "opt-wrong"
                icon = "❌"
            else:
                icon = ""
                
            st.markdown(f'<div class="opt-box {style_class}">{icon} {opt}</div>', unsafe_allow_html=True)

        # 2. 下方弹出结果面板
        box_class = "result-correct" if my_ans == real_ans else "result-wrong"
        msg = "回答正确！" if my_ans == real_ans else f"回答错误！正确答案是 {real_ans}"
        
        st.markdown(f"""
        <div class="result-box {box_class}">
            <h4>{msg}</h4>
            <hr style="margin:10px 0; border-color:#ccc; opacity:0.5;">
            <b>💡 记忆口诀：</b>{q['guide']}<br>
            <b>📖 详细解析：</b><br>{q['exp']}
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        if st.button("下一题 ➡️", type="primary"):
            st.session_state.idx += 1
            st.session_state.submitted = False
            st.rerun()