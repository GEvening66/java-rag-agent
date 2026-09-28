"""L5 接口层：HTTP（FastAPI）/ CLI / Streamlit 调试界面 + 前端静态页。

允许依赖：下面所有层。这是唯一允许"从外向内取数"的地方，也是唯一允许
出现 Web 框架（fastapi / streamlit / pydantic）的地方——见 tests/test_architecture.py。
"""
