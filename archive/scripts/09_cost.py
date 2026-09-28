"""
第 5 课 5b：成本统计 —— "跑一次问答多少钱？"（面试必问）

运行方式（在 demo5 目录下）：
    python scripts/09_cost.py

用评测集前 5 个问题做样本，统计每次 API 调用的 token 数并估算成本。
（embedding 用的硅基流动免费额度，成本主要来自生成调用）

你的任务：补全 estimate_cost 函数（3 行）。
"""

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
chat_client = mod.chat_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

# DeepSeek 价格（近似值，元/百万 token；以官网最新价格为准）
PRICE_INPUT = 2.0    # 输入（缓存未命中）
PRICE_OUTPUT = 8.0   # 输出

EVAL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "eval", "eval_questions.json")
)
N_SAMPLE = 5  # 抽样题数


# ================= 你的任务：补全这个函数 =================
def estimate_cost(prompt_tokens, completion_tokens):
    """
    按 DeepSeek 价格估算一次调用的成本（元）。

    公式：
    成本 = prompt_tokens / 1_000_000 * PRICE_INPUT
         + completion_tokens / 1_000_000 * PRICE_OUTPUT
    """
    # TODO: 在这里写你的实现（3 行）
    cost = prompt_tokens / 1_000_000 * PRICE_INPUT + completion_tokens / 1_000_000 * PRICE_OUTPUT
    return cost
# ==========================================================


def main():
    with open(EVAL_PATH, encoding="utf-8") as f:
        questions = json.load(f)[:N_SAMPLE]

    total_cost = 0.0
    total_tokens = 0
    for q in questions:
        resp = chat_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": q["question"]}],
        )
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        cost = estimate_cost(prompt_tokens, completion_tokens)
        total_cost += cost
        total_tokens += prompt_tokens + completion_tokens
        print(f"[{q['question'][:20]}...] 输入 {prompt_tokens} + 输出 {completion_tokens} token，约 ¥{cost:.4f}")

    avg = total_cost / N_SAMPLE
    print(f"\n样本 {N_SAMPLE} 题，共 {total_tokens} token，总成本约 ¥{total_cost:.4f}")
    print(f"平均每次问答约 ¥{avg:.4f}（≈ {avg * 100:.2f} 分钱）")
    print("\n说明：价格是近似值（以官网为准）；embedding 免费；")
    print("真实问答还包含检索工具调用等 token，这里是最小口径。")


if __name__ == "__main__":
    main()
