"""服务入口（兼容写法）：`uvicorn api:app --port 8000`。

真正的实现在 **agent/serving/api.py**（接口层）。这里只做一层转发：
部署命令短，且 `uvicorn agent.serving.api:app` 同样可用（两种写法等价）。
"""
from agent.serving.api import app  # noqa: F401

__all__ = ["app"]
