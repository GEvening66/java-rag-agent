"""全局配置：路径、模型、阈值集中一处，其他模块只从这里读。

为什么要集中：之前每个脚本各写一遍 Key/路径/阈值，改一处要改十处。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402  （项目根目录的 config.py，已被 .gitignore 忽略）

# ---------- 路径 ----------
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, "cache")
MEMORY_DIR = os.path.join(ROOT, "memory")
EVAL_PATH = os.path.join(ROOT, "eval", "eval_questions.json")

# ---------- 模型 ----------
DEEPSEEK_API_KEY = config.DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL = config.DEEPSEEK_BASE_URL
DEEPSEEK_MODEL = config.DEEPSEEK_MODEL
EMBEDDING_API_KEY = config.SILICONFLOW_API_KEY
EMBEDDING_BASE_URL = config.SILICONFLOW_BASE_URL
EMBEDDING_MODEL = config.EMBEDDING_MODEL

# ---------- 切分 / 检索 ----------
CHUNK_SIZE = 500
OVERLAP = 100
TOP_K = 5
TOOL_SNIPPET_CHARS = 500  # 工具返回的单块截断长度（太短会让模型反复检索）

# ---------- 两级检索：粗召回 + Cross-Encoder 重排 ----------
RECALL_K = 50          # 粗召回条数（cross-encoder 的候选集大小）
                       # 实测依据：20→50 让"证据块排第 25 名"的题恢复命中，rerank token 成本几乎不变
USE_RERANK = True      # 是否启用重排（rerank 失败会自动回退为向量顺序）
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

# ---------- 护栏与循环上限（agent 循环必须有界）----------
GROUNDING_PASS = 0.5    # 引用接地率：通过阈值
GROUNDING_MIN = 0.25    # 越权判定：整体接地率低于它 = 越权标注
MAX_TOOL_STEPS = 5      # 工具循环上限
MAX_QA_ROUNDS = 3       # 质检总轮数上限
MAX_MEMORY = 20         # 单用户记忆条数上限

# ---------- 失败恢复 ----------
LLM_TIMEOUT = 60        # 单次调用超时（秒）
RETRY_MAX = 3           # 最大重试次数（指数退避 + 抖动）
RETRY_BASE_DELAY = 0.8  # 退避基数（秒）：0.8 → 1.6 → 3.2

# ---------- 记忆 ----------
MEMORY_K = 2            # 每次注入的记忆条数上限
MEMORY_MIN_SIM = 0.35   # 记忆检索相似度阈值：低于它不注入（防无关记忆干扰）
