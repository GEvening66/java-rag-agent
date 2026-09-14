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

# ---------- 护栏与循环上限（agent 循环必须有界）----------
GROUNDING_PASS = 0.5    # 引用接地率：通过阈值
GROUNDING_MIN = 0.25    # 越权判定：整体接地率低于它 = 越权标注
MAX_TOOL_STEPS = 5      # 工具循环上限
MAX_QA_ROUNDS = 3       # 质检总轮数上限
MAX_MEMORY = 20         # 单用户记忆条数上限
