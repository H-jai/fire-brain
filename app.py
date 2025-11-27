import streamlit as st
import pymysql
import ssl
import ast
from datetime import datetime
import time

# TiDB 配置
TIDB_CONFIG = {
    "host": "gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
    "port": 4000,
    "user": "2emKBRzbZrLBNax.root",
    "password": "Bh2VO3dlAEnhbv4G",
    "database": "test",
}

# --- 数据库连接 (带缓存) ---
@st.cache_resource
def get_db_pool():
    """获取数据库连接池，避免重复握手"""
    try:
        return pymysql.connect(
            **TIDB_CONFIG,
            ssl={"check_hostname": False, "verify_mode": ssl.CERT_NONE},
            autocommit=True,
            connect_timeout=3
        )
    except Exception as e:
        return None

# --- 优化：一次性拉取题目 ---
@st.cache_data(ttl=600)
def fetch_questions(source_type, limit=50):
    conn = get_db_pool()
    if not conn: return []
    
    questions = []
    try:
        # 即使连接断开也会自动重连
        conn.ping(reconnect=True)
        with conn.cursor() as cursor:
            if source_type == "mistake":
                sql = """SELECT DISTINCT q.id, q.question, q.options, q.answer, q.explanation, q.beginner_guide, q.source_type 
                         FROM question_bank q JOIN study_record s ON q.id=s.question_id 
                         WHERE s.is_correct=0 ORDER BY s.study_date DESC LIMIT %s"""
                cursor.execute(sql, (limit,))
            else:
                sql = """SELECT id, question, options, answer, explanation, beginner_guide, source_type 
                         FROM question_bank WHERE source_type=%s ORDER BY RAND() LIMIT %s"""
                cursor.execute(sql, (source_type, limit))
            
            for row in cursor.fetchall():
                # 🔥 关键修复：确保 options 被正确解析为列表
                raw_opt = row[2]
                try:
                    opts = ast.literal_eval(raw_opt)
                    if not isinstance(opts, list):
                        opts = [str(raw_opt)] # 兜底
                except:
                    # 如果数据库里存的是纯字符串，尝试按特定分隔符分割，或者直接当做一个选项
                    opts = [str(raw_opt)]
                
                questions.append({
                    "id": row[0], "q": row[1], "opts": opts, "ans": row[3], 
                    "exp": row[4], "guide": row[5], "type": row[6]
                })
    except Exception as e:
        st.error(f"网络连接错误: {e}")
    return questions

# --- 优化：答案暂存与批量上传 ---
# 为了速度，我们不每题都写库，而是先存在 session_state 里
# 只有在用户退出或达到一定数量时才后台写库（这里简化为即时写库但做异常处理）
def save_answer_async(q_id, user_ans, is_correct):
    if 'unsaved_records' not in st.session_state:
        st.session_state.unsaved_records = []
    
    st.session_state.unsaved_records.append({
        "question_id": q_id,
        "user_answer": user_ans,
        "is_correct": 1 if is_correct else 0
    })

    # 简单的后台同步策略：每3题同步一次，或者页面刷新时同步
    if len(st.session_state.unsaved_records) >= 1:
        sync_records()

def sync_records():
    """将暂存的做题记录同步到云端"""
    if not st.session_state.get('unsaved_records'): return
    
    conn = get_db_pool()
    if conn:
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as cursor:
                sql = "INSERT INTO study_record (question_id, user_answer, is_correct) VALUES (%s, %s, %s)"
                data = [(r['question_id'], r['user_answer'], r['is_correct']) for r in st.session_state.unsaved_records]
                cursor.executemany(sql, data)
            st.session_state.unsaved_records = [] # 清空队列
        except:
            pass # 失败了下次再说，别卡用户界面

# --- 页面设置 ---
st.set_page_config(page_title="消防大脑Pro", page_icon="🔥", layout="centered")

st.markdown("""
<style>
    .stButton>button { width: 100%; height: 50px; border-radius: 12px; font-size: 16px; transition: 0.2s; }
    .stButton>button:hover { transform: scale(1.02); }
    .result-box { padding: 20px; border-radius: 10px; margin-top: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .result-correct { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
    .result-wrong { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
    
    /* 选项样式优化 */
    .opt-container { display: flex; flex-direction: column; gap: 10px; }
    .opt-item { padding: 12px 15px; border-radius: 8px; border: 1px solid #e5e7eb; background: white; margin-bottom: 8px; }
    .opt-correct { background-color: #dcfce7 !important; border-color: #22c55e !important; }
    .opt-wrong { background-color: #fee2e2 !important; border-color: #ef4444 !important; opacity: 0.8; }
</style>
""", unsafe_allow_html=True)

# 状态初始化
if 'page' not in st.session_state: st.session_state.page = "home"
if 'q_list' not in st.session_state: st.session_state.q_list = []
if 'idx' not in st.session_state: st.session_state.idx = 0
if 'score' not in st.session_state: st.session_state.score = 0
if 'submitted' not in st.session_state: st.session_state.submitted = False

# 🏠 首页
if st.session_state.page == "home":
    st.title("🔥 消防大脑 V7 (极速版)")
    st.markdown("### 智能刷题系统")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📚 场景化练习\n(普通资料)", key="btn_normal"):
            with st.spinner("正在加载题库..."):
                st.session_state.q_list = fetch_questions("普通资料", 50)
                st.session_state.page = "quiz"
                st.session_state.idx = 0
                st.session_state.score = 0
                st.session_state.submitted = False
                st.rerun()
            
    with col2:
        if st.button("💯 真题模拟\n(历年真题)", key="btn_real"):
            with st.spinner("正在加载真题..."):
                st.session_state.q_list = fetch_questions("历年真题", 50)
                st.session_state.page = "quiz"
                st.session_state.idx = 0
                st.session_state.score = 0
                st.rerun()

    if st.button("📒 攻克错题 (复习模式)", type="secondary"):
        st.session_state.q_list = fetch_questions("mistake", 30)
        st.session_state.page = "quiz"
        st.session_state.idx = 0
        st.session_state.score = 0
        st.rerun()

# 📝 做题页
elif st.session_state.page == "quiz":
    if not st.session_state.q_list:
        st.warning("⚠️ 暂无题目，请先在电脑端上传资料！")
        if st.button("返回"): 
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    q_data = st.session_state.q_list
    idx = st.session_state.idx
    total = len(q_data)

    # 结算页
    if idx >= total:
        sync_records() # 确保最后一次同步完成
        st.balloons()
        st.success("🎉 练习完成！")
        st.metric("最终得分", f"{st.session_state.score}", f"共 {total} 题")
        if st.button("🏠 返回首页"):
            st.session_state.page = "home"
            st.rerun()
        st.stop()

    q = q_data[idx]
    
    # 顶部进度条
    progress = (idx + 1) / total
    st.progress(progress)
    st.caption(f"进度: {idx+1} / {total}")

    # 题目显示
    st.markdown(f"#### {q['q']}")

    # 选项逻辑
    # 如果已提交，显示带颜色的结果；如果未提交，显示单选框
    if not st.session_state.submitted:
        # 使用 form 来包含选项和提交按钮，虽然 Streamlit form 有时会稍慢，但逻辑更清晰
        # 这里为了极速反馈，直接用 radio + button
        
        # 渲染选项：确保如果 options 包含 A. B. 前缀，我们处理一下显示
        formatted_opts = q['opts']
        
        choice = st.radio("请选择:", formatted_opts, index=None, key=f"q_{idx}", label_visibility="collapsed")
        
        # 留白
        st.write("") 
        
        if st.button("提交答案", type="primary", use_container_width=True):
            if choice:
                st.session_state.user_choice = choice
                st.session_state.submitted = True
                
                # 判定逻辑
                real_ans = q['ans'].strip().upper()
                # 提取选项的第一个字母 (如 "A. xxx" -> "A")
                my_ans_char = choice[0].strip().upper()
                is_correct = (real_ans == my_ans_char)
                
                if is_correct: st.session_state.score += 1
                
                # 异步保存，不卡界面
                save_answer_async(q['id'], my_ans_char, is_correct)
                
                st.rerun()
            else:
                st.toast("请先选择一个选项 👇")

    else:
        # --- 结果展示界面 (已提交) ---
        real_ans = q['ans'].strip().upper()
        my_ans_char = st.session_state.user_choice[0].strip().upper()
        is_correct = (real_ans == my_ans_char)

        # 自定义渲染选项列表
        for opt in q['opts']:
            opt_char = opt[0].strip().upper()
            style = "opt-item"
            prefix = ""
            
            if opt_char == real_ans:
                style += " opt-correct"
                prefix = "✅ "
            elif opt_char == my_ans_char and not is_correct:
                style += " opt-wrong"
                prefix = "❌ "
                
            st.markdown(f'<div class="{style}">{prefix}{opt}</div>', unsafe_allow_html=True)

        # 解析区域
        box_class = "result-correct" if is_correct else "result-wrong"
        msg = "回答正确！" if is_correct else f"正确答案是 【{real_ans}】"
        
        st.markdown(f"""
        <div class="result-box {box_class}">
            <h4 style="margin:0">{msg}</h4>
            <hr style="margin:10px 0; opacity:0.2">
            <p><b>🔑 记忆口诀：</b>{q['guide']}</p>
            <p style="font-size:14px; opacity:0.8">{q['exp']}</p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("下一题 ➡️", type="primary", use_container_width=True):
            st.session_state.idx += 1
            st.session_state.submitted = False
            st.rerun()
