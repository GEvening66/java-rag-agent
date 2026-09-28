"""统一入口：python -m agent <子命令>

     ask      "问题"            基础 RAG（检索 + 引用校验）
     tool     "问题"            工具调用 Agent（function calling）
     qa       "问题"            质检 Agent（多 Agent 编排）
     memory   "问题" --user u1  带长期记忆的问答
     clarify                    交互式澄清问答
     eval     retrieval|e2e|cost 分层评测
     metrics                    可观测性指标（读 logs/traces.jsonl）
     app                        提示如何启动 Web 界面
"""
import argparse
import json

from ..core import observability
from ..evaluation import evaluate
from ..pipeline import clarify, memory, qa, rag, tools
from ..retrieval import index as index_mod


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
    p.add_argument("which", choices=["retrieval", "e2e", "cost", "evidence"])
    p = sub.add_parser("diag", help="单题诊断：定位某题为什么没检索到（参数=评测集题号）")
    p.add_argument("no", type=int)
    sub.add_parser("metrics", help="可观测性指标（平均轮次/重复调用率/P95 延迟/token）")
    p = sub.add_parser("forget", help="删除某用户全部记忆（被遗忘权）")
    p.add_argument("--user", default="demo_user")
    p = sub.add_parser("export", help="导出某用户记忆（数据可携带权）")
    p.add_argument("--user", default="demo_user")
    sub.add_parser("app", help="Web 界面启动方式")

    args = parser.parse_args(argv)

    if args.cmd == "app":
        print("Web 界面：streamlit run web.py")
        return
    if args.cmd == "metrics":
        print(json.dumps(observability.metrics(), ensure_ascii=False, indent=2))
        return
    if args.cmd == "eval" and args.which == "evidence":
        # 证据句自检：只读 cache/chunks.json，不需要任何 API
        evaluate.evidence_check()
        return
    if args.cmd == "diag":
        from ..evaluation import diagnose as diagnose_mod
        diagnose_mod.diagnose(args.no)
        return
    if args.cmd == "forget":
        removed = memory.delete_user(args.user)
        print(f"[记忆] 已删除用户 {args.user} 的记忆" if removed
              else f"[记忆] 用户 {args.user} 没有记忆文件")
        return
    if args.cmd == "export":
        print(json.dumps(memory.export_user(args.user), ensure_ascii=False, indent=2))
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
