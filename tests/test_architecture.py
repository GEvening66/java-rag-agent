"""架构护栏：用测试锁住分层的依赖方向（防止以后随手 import 把分层腐化）。

规则（依赖只能自上而下）：
    core ← retrieval ← pipeline ← evaluation ← serving

具体断言：
1. 每层只能依赖"自己 + 自己下面"的层；
2. `core` 不依赖任何上层（它是底座）；
3. `evaluation` / `serving` 不被上层反向依赖（评测与接口都不能进主链路）；
4. Web 框架（fastapi / streamlit / pydantic）只允许出现在 serving 层；
5. 旧的 `agent/agents/` 包已被 pipeline 取代，不应复活。

为什么值得写这个测试：分层是靠"约束"维持的，不是靠自觉。
没有它，三个月后一句 `from .serving import ...` 就会把结构毁掉，而且没人会发现。
"""
import ast
import io
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT = os.path.join(ROOT, "agent")

LAYERS = ["core", "retrieval", "pipeline", "evaluation", "serving"]

# 每层允许依赖的层（不含自身；自身永远允许）
ALLOWED = {
    "core": set(),
    "retrieval": {"core"},
    "pipeline": {"core", "retrieval"},
    "evaluation": {"core", "retrieval", "pipeline"},
    "serving": {"core", "retrieval", "pipeline", "evaluation"},
}

WEB_FRAMEWORKS = {"fastapi", "streamlit", "uvicorn", "pydantic"}


def _modules(layer):
    d = os.path.join(AGENT, layer)
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".py")]


def _target_layer(dotted):
    """把 'agent.core.llm' 这样的绝对路径解析成层名；不是本项目的模块返回 None。"""
    parts = dotted.split(".")
    if len(parts) > 1 and parts[0] == "agent" and parts[1] in LAYERS:
        return parts[1]
    return None


def _imports(path, layer):
    """返回该文件 import 到的 (层名集合, 顶层包名集合)。"""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    layers, tops = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:                      # 相对导入
                if node.level == 1:             # from . import x   → agent.<layer>
                    base = f"agent.{layer}"
                elif node.level == 2:           # from ..core import x → agent.core
                    base = "agent"
                else:                           # 越过 agent 包，非法
                    layers.add("<超出 agent 包>")
                    continue
                dotted = base + (f".{node.module}" if node.module else "")
            else:
                dotted = node.module or ""
            tops.add(dotted.split(".")[0])
            got = _target_layer(dotted)
            if got:
                layers.add(got)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                tops.add(alias.name.split(".")[0])
                got = _target_layer(alias.name)
                if got:
                    layers.add(got)
    return layers, tops


@pytest.mark.parametrize("layer", LAYERS)
def test_dependencies_point_downward_only(layer):
    violations = []
    for path in _modules(layer):
        imported, _ = _imports(path, layer)
        for target in sorted(imported):
            if target == layer or target in ALLOWED[layer]:
                continue
            violations.append(f"{os.path.relpath(path, ROOT)} → 依赖了上层 {target}")
    assert not violations, "分层倒挂：\n" + "\n".join(violations)


def test_core_has_no_upward_dependency():
    """core 是底座：它只能依赖自己和第三方库。"""
    for path in _modules("core"):
        imported, _ = _imports(path, "core")
        assert not (imported - {"core"}), f"{os.path.relpath(path, ROOT)} 不该依赖 {imported - {'core'}}"


def test_evaluation_and_serving_are_not_imported_by_main_pipeline():
    """评测层与接口层不能出现在主链路里（否则每次问答都多花钱 / 多依赖 Web 框架）。"""
    for layer in ("core", "retrieval", "pipeline"):
        for path in _modules(layer):
            imported, _ = _imports(path, layer)
            bad = imported & {"evaluation", "serving"}
            assert not bad, f"{os.path.relpath(path, ROOT)} 反向依赖了 {bad}"


def test_web_frameworks_only_in_serving_layer():
    """核心链路应保持与 Web 框架无关：能命令行跑、能评测跑，也能被别的服务复用。"""
    for layer in ("core", "retrieval", "pipeline", "evaluation"):
        for path in _modules(layer):
            _, tops = _imports(path, layer)
            assert not (tops & WEB_FRAMEWORKS), \
                f"{os.path.relpath(path, ROOT)} 引入了 Web 框架 {tops & WEB_FRAMEWORKS}"


def test_every_layer_has_init_and_legacy_package_is_gone():
    for layer in LAYERS:
        assert os.path.exists(os.path.join(AGENT, layer, "__init__.py")), f"{layer}/ 缺少 __init__.py"
    assert not os.path.exists(os.path.join(AGENT, "agents")), \
        "旧的 agent/agents/ 应已被 agent/pipeline/ 取代（不要再把它加回来）"
