"""Web 界面（Streamlit）：基于 agent/ 完整链路的聊天式 UI。

启动方式（在项目根目录 demo5 下）：
    streamlit run web.py

链路可选：
  质检 Agent（多 Agent：工具调用 + 评分归因 + 分流重试）
  工具 Agent（function calling）
  基础 RAG（检索 + 引用接地率校验 + 反思重答）
侧边栏还展示可观测指标（来自 logs/traces.jsonl）。
"""
import streamlit as st

from agent.core import observability, settings
from agent.pipeline import clarify, memory as memory_agent, qa, rag, tools
from agent.retrieval import index as index_mod

st.set_page_config(page_title="Java 学习 Agent", page_icon="🤖", layout="centered")
st.title("🤖 Java 学习 Agent")
st.caption("RAG · 工具调用 · 质检 Agent（多 Agent）· 引用护栏 · 长期记忆 · 可观测性")


@st.cache_resource
def get_index():
    """索引只构建一次（Streamlit 每次交互都会重跑脚本）。"""
    return index_mod.build_index()


def last_trace_summary():
    """读最后一条 trace，格式化成一行摘要。"""
    traces = observability.load_traces()
    if not traces:
        return ""
    t = traces[-1]
    spans = t.get("spans", [])
    tool_spans = [s for s in spans if s["name"] == "tool"]
    dups = sum(1 for s in tool_spans if s.get("duplicate"))
    tokens = sum(s.get("tokens", 0) for s in spans if s["name"] == "llm")
    return (f"trace {t['trace_id']} · 工具 {len(tool_spans)} 次（重复 {dups}）"
            f" · {t.get('total_ms', 0)}ms · {tokens} token")


index = get_index()

# ---------------- 侧边栏：配置 + 知识库 + 可观测指标 ----------------
with st.sidebar:
    st.markdown("### ⚙️ 运行配置")
    mode = st.selectbox("链路模式", [
        "质检 Agent（多 Agent，推荐）",
        "工具 Agent（function calling）",
        "基础 RAG（检索 + 引用校验）",
    ])
    use_memory = st.checkbox("启用长期记忆（跨会话）", value=False)
    user_id = st.text_input("用户 ID", value="u1", disabled=not use_memory)

    st.markdown("---")
    st.markdown("### 📚 知识库")
    chunks, _vecs = index
    st.markdown(f"- 数据块：**{len(chunks)}**")
    st.markdown(f"- 检索 top-k：**{settings.TOP_K}**")
    st.markdown(f"- 单块返回上限：**{settings.TOOL_SNIPPET_CHARS}** 字")

    st.markdown("---")
    st.markdown("### 📊 可观测指标")
    m = observability.metrics()
    if m.get("traces"):
        st.markdown(f"- 问答次数：**{m['traces']}**")
        st.markdown(f"- 平均轮次：**{m['avg_steps']}**")
        st.markdown(f"- 重复调用率：**{m['duplicate_rate']:.0%}**")
        st.markdown(f"- 超上限率：**{m['hit_max_steps_rate']:.0%}**")
        st.markdown(f"- P95 延迟：**{m['p95_ms']} ms**")
        st.markdown(f"- 平均 token：**{m['avg_tokens']}**")
    else:
        st.caption("还没有 trace，先问一个问题")

# ---------------- 会话状态（记忆要素） ----------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None


def answer_once(question):
    """按侧边栏选择走对应链路（verbose=False：日志进终端，不污染界面）。"""
    if use_memory:
        return memory_agent.run(question, user_id or "u1", index, verbose=False)
    if mode.startswith("质检"):
        return qa.run(question, index, verbose=False)
    if mode.startswith("工具"):
        return tools.run(question, index, verbose=False)
    answer, citations, _ = rag.answer(question, index, verbose=False)
    return f"{answer}\n\n引用：{citations}"


def agent_reply(user_input):
    """三分支：等待澄清 → 触发澄清 → 直接回答。"""
    if st.session_state.pending:
        full = f"{st.session_state.pending}，具体是：{user_input}"
        st.session_state.pending = None
        return answer_once(full)
    if clarify.needs_clarification(user_input):
        st.session_state.pending = user_input
        return clarify.CLARIFY_TEXT
    return answer_once(user_input)


# ---------------- 渲染历史 ----------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------- 输入 ----------------
user_input = st.chat_input("问一个 Java 问题，例如：HashMap 的负载因子是多少？")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("思考中…（多 Agent 链路会多花几秒）"):
            reply = agent_reply(user_input)
        st.markdown(reply)
        summary = last_trace_summary()
        if summary:
            st.caption("🔍 " + summary)

    st.session_state.messages.append({"role": "assistant", "content": reply})
