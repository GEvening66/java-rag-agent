"""统一入口：python -m agent <子命令>

     ask      "问题"            基础 RAG（检索 + 引用校验）
     tool     "问题"            工具调用 Agent（function calling）
     qa       "问题"            质检 Agent（多 Agent 编排）
     memory   "问题" --user u1  带长期记忆的问答
     clarify                    交互式澄清问答
     eval     retrieval|e2e|cost 分层评测
     app                        提示如何启动 Web 界面
"""
import argparse

from . import evaluate
from . import index as index_mod
from .agents import clarify, memory, qa, rag, tools


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent", description="Java-RAG-Agent 统一入口")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", help="基础 RAG 问答")
    p.add_argument("question")
    p = sub.add_parser("tool", help="工具调用 Agent")
    p.add_argument("question")
    p = sub.add_parser("qa", help="质检 Agent（多 Agent 编排）")
    p.add_argument("question")
    p = sub.add_parser("memory", help="带长期记忆的问答")
    p.add_argument("question")
    p.add_argument("--user", default="demo_user")
    sub.add_parser("clarify", help="交互式澄清问答")
    p = sub.add_parser("eval", help="分层评测")
    p.add_argument("which", choices=["retrieval", "e2e", "cost"])
    sub.add_parser("app", help="Web 界面启动方式")

    args = parser.parse_args(argv)

    if args.cmd == "app":
        print("Web 界面：streamlit run scripts/06_app.py")
        return

    index = index_mod.build_index()

    if args.cmd == "clarify":
        clarify.run(index)
    elif args.cmd == "ask":
        answer, citations, _ = rag.answer(args.question, index)
        print(f"\n回答：{answer}\n引用：{citations}")
    elif args.cmd == "tool":
        print("\n" + tools.run(args.question, index))
    elif args.cmd == "qa":
        print("\n===== 质检后最终回答 =====\n" + qa.run(args.question, index))
    elif args.cmd == "memory":
        print("\n===== 回答 =====\n" + memory.run(args.question, args.user, index))
    elif args.cmd == "eval":
        if args.which == "retrieval":
            evaluate.retrieval_eval(index)
        elif args.which == "e2e":
            evaluate.e2e_eval(index)
        else:
            evaluate.cost_eval()


if __name__ == "__main__":
    main()
