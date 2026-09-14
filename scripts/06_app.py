"""
第 4 课 4c：Streamlit 界面 —— 把你的 agent 变成可演示的 Web 应用

运行方式（在 demo5 目录下，先装依赖）：
    pip install streamlit
    streamlit run scripts/06_app.py
    （浏览器会自动打开 http://localhost:8501）

功能：聊天式界面 + 模糊问题澄清（记忆）+ 引用溯源回答
你的任务：补全 agent_reply 函数（8~10 行）。
"""

import importlib.util
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "clarify", os.path.join(os.path.dirname(__file__), "05_clarify.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ask = mod.ask
needs_clarification = mod.needs_clarification
K = mod.K


sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod2)
embed_texts = mod2.embed_texts
build_index = mod2.build_index
search_top_k = mod2.search_top_k
chat_client = mod2.chat_client

st.set_page_config(page_title="Java 学习 Agent", page_icon="🤖")
st.title("🤖 Java 学习 Agent")
st.caption("RAG + 引用溯源校验 + 模糊问题澄清 —— 面试 demo")


# ============ 会话状态（agent 的"记忆"要素）============
# Streamlit 每次交互都会重新执行脚本，session_state 是它"记住"跨轮次数据的地方
if "messages" not in st.session_state:
    st.session_state.messages = []   # 聊天历史
if "pending" not in st.session_state:
    st.session_state.pending = None  # 等待澄清的原始问题


# ================= 你的任务：补全这个函数 =================
def agent_reply(user_input):
    """
    生成 agent 回复。逻辑（3 个分支）：
    1. 如果 pending 不为空（上一轮是澄清提问）：
       把用户新输入拼进原始问题 -> f"{pending}，具体是：{user_input}"
       -> 清空 pending -> 返回 ask(完整问题)
    2. 如果 needs_clarification(user_input)：
       把 user_input 存进 pending -> 返回澄清提问文本
       （提示：跟 05_clarify.py 里打印的那句澄清语保持一致）
    3. 否则：直接返回 ask(user_input)
    """
    # TODO: 在这里写你的实现（8~10 行）
    if st.session_state.pending is not None:
        user_input = f"{st.session_state.pending}，具体是：{user_input}"   
        st.session_state.pending = None
        return ask(user_input)
        
    elif needs_clarification(user_input):
        st.session_state.pending = user_input
        return "这个问题比较宽泛，你想具体了解哪个方面？（比如：存储结构 / 负载因子与扩容 / 线程安全 / ...）"
    else:
        return ask(user_input)



def main():
    # 渲染历史消息（记忆回放）
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    chunks=build_index()  # 预热索引（有缓存很快）
    chunks_num=len(chunks)
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    files = os.listdir(DATA_DIR)
    len_files = len(files)
    with st.sidebar:
        st.markdown(f"**数据块数量：** {chunks_num}")
        st.markdown(f"**数据文件数量：** {len_files}")
        st.markdown(f"**检索 top-k：** {K}")
        st.markdown("---")
        st.markdown("数据文件列表：")
        for f in files:
            st.markdown(f"- {f}")
    

    user_input = st.chat_input("问一个 Java 问题，例如：HashMap 的负载因子是多少？")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                reply = agent_reply(user_input)
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
