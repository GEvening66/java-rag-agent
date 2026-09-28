"""可观测性：Trace / Span / 指标聚合 / 工具结果去重。

零依赖实现（只用标准库），落盘 JSON Lines，可离线聚合、可回放失败案例。

- 一次问答 = 一个 Trace（trace_id 唯一）
- 每个步骤 = 一个 Span（LLM 调用 / 工具调用），带耗时与关键属性
- 工具调用用 (工具名, 参数哈希) 去重：重复调用命中缓存 + 提示模型纠偏
- metrics() 从 trace 聚合：平均轮次、重复调用率、超上限率、P50/P95 延迟、token
"""
import hashlib
import json
import os
import time
import uuid

from . import settings

TRACE_DIR = settings.LOG_DIR
TRACE_FILE = os.path.join(TRACE_DIR, "traces.jsonl")


def _hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def arg_hash(args):
    """参数稳定哈希（键序无关）——用于重复调用检测。"""
    return _hash(json.dumps(args, sort_keys=True, ensure_ascii=False))


def result_hash(text):
    """结果哈希——用于判断"同参数是否返回了同样内容"。"""
    return _hash(text)


class Trace:
    """一次问答的完整链路。"""

    def __init__(self, kind, input_text=""):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.input = str(input_text)[:200]
        self.t0 = time.time()
        self.spans = []

    def add_span(self, name, ms, attrs=None):
        self.spans.append({"name": name, "ms": round(ms, 1), **(attrs or {})})

    def finish(self, output="", **meta):
        """落盘并返回记录。"""
        rec = {
            "trace_id": self.id,
            "kind": self.kind,
            "input": self.input,
            "output": str(output)[:200],
            "total_ms": round((time.time() - self.t0) * 1000, 1),
            "spans": self.spans,
            **meta,
        }
        _append(rec)
        return rec

    def summary(self):
        """一行摘要，方便命令行直接看。"""
        llm_spans = [s for s in self.spans if s["name"] == "llm"]
        tool_spans = [s for s in self.spans if s["name"] == "tool"]
        dups = sum(1 for s in tool_spans if s.get("duplicate"))
        tokens = sum(s.get("tokens", 0) for s in llm_spans)
        ms = round((time.time() - self.t0) * 1000)
        return (f"[trace {self.id}] 轮次 {len(llm_spans)} · 工具 {len(tool_spans)} 次"
                f"（重复 {dups}） · {ms}ms · {tokens} token")


def _append(rec):
    os.makedirs(TRACE_DIR, exist_ok=True)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_traces():
    """读回所有 trace（离线分析用）。"""
    if not os.path.exists(TRACE_FILE):
        return []
    with open(TRACE_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def metrics(traces=None):
    """聚合指标。传入 traces 便于测试；不传则读盘。"""
    traces = load_traces() if traces is None else traces
    n = len(traces)
    if n == 0:
        return {"traces": 0}

    steps, tool_calls, dups, tokens, times, tool_usage, hit_max = [], 0, 0, 0, [], {}, 0
    for t in traces:
        spans = t.get("spans", [])
        llm_spans = [s for s in spans if s["name"] == "llm"]
        tool_spans = [s for s in spans if s["name"] == "tool"]
        steps.append(len(llm_spans))
        tool_calls += len(tool_spans)
        dups += sum(1 for s in tool_spans if s.get("duplicate"))
        tokens += sum(s.get("tokens", 0) for s in llm_spans)
        times.append(t.get("total_ms", 0))
        hit_max += 1 if t.get("hit_max_steps") else 0
        for s in tool_spans:
            tool_usage[s.get("tool", "?")] = tool_usage.get(s.get("tool", "?"), 0) + 1

    ordered = sorted(times)

    def percentile(p):
        idx = min(int(len(ordered) * p), len(ordered) - 1)
        return round(ordered[idx], 1)

    return {
        "traces": n,
        "avg_steps": round(sum(steps) / n, 2),
        "tool_calls": tool_calls,
        "duplicate_rate": round(dups / tool_calls, 3) if tool_calls else 0.0,
        "hit_max_steps_rate": round(hit_max / n, 3),
        "avg_total_ms": round(sum(times) / n, 1),
        "p50_ms": percentile(0.5),
        "p95_ms": percentile(0.95),
        "avg_tokens": round(tokens / n, 1),
        "tool_usage": tool_usage,
    }
