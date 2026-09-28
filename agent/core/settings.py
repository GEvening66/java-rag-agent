"""全局配置：路径、模型、阈值集中一处，core / retrieval / pipeline / evaluation / serving 都只从这里读。

为什么要集中：之前每个脚本各写一遍 Key/路径/阈值，改一处要改十处。

为什么路径不靠"文件在第几层"数目录：用**向上找项目根标记**的方式定位根目录——
模块被移进分层子包时，cache / logs / memory 不会静默指到错误位置（分层重构最容易踩的坑）。
"""
import os
import sys

_MARKERS = ("requirements.txt", "config.example.py")   # 项目根目录的标记文件


def _find_root(start):
    """从 start 向上找含根标记的目录；找不到则返回 start。"""
    cur = start
    for _ in range(6):
        if any(os.path.exists(os.path.join(cur, m)) for m in _MARKERS):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:      # 已到盘符根
            break
        cur = parent
    return start


# 部署/多实例时可用环境变量显式覆盖
ROOT = os.environ.get("AGENT_ROOT") or _find_root(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import config  # noqa: E402  （项目根目录的 config.py，已被 .gitignore 忽略）
except ImportError as exc:      # 新 clone 的仓库只有 config.example.py
    raise SystemExit(
        "缺少配置文件：请把 config.example.py 复制为 config.py 并填入 API Key。\n"
        f"期望位置：{os.path.join(ROOT, 'config.py')}"
    ) from exc

# ---------- 路径 ----------
DATA_DIR = os.path.join(ROOT, "data")
RUNTIME_DIR = os.path.join(ROOT, "runtime")          # 运行时产物集中一处，便于 gitignore 与清理
CACHE_DIR = os.path.join(RUNTIME_DIR, "cache")       # 向量索引缓存
LOG_DIR = os.path.join(RUNTIME_DIR, "logs")          # trace 落盘
MEMORY_DIR = os.path.join(RUNTIME_DIR, "memory")     # 长期记忆（按用户一个文件）
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

# ---------- 混合检索（向量 + BM25，RRF 融合）----------
USE_HYBRID = True      # 实测依据：解决"专有符号 token"召回问题（java.lang.StackOverflowError 排第 90 名）
RRF_K = 60             # RRF 平滑常数（只用排名、不用分数，免调权重）

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
