"""测试环境变量需在导入 app 之前生效，避免本地 .env 干扰断言。"""

import os

os.environ["AUTH_ENABLED"] = "true"
os.environ["AUTH_USERNAME"] = "tester"
os.environ["AUTH_PASSWORD"] = "test-pass"
os.environ["AUTH_SECRET_KEY"] = "unit-test-secret"
os.environ["AI_API_BASE_URL"] = "http://127.0.0.1:9"
os.environ["AI_API_KEY"] = "test-key"
os.environ["AI_MODEL"] = "test-model"
os.environ["AI_MODELS"] = "test-model,other-model"
os.environ["AGENT_ENABLED"] = "false"
os.environ["MOM_PROJECTS"] = ""
os.environ["MOM_DB_HOST"] = ""
os.environ["MOM_KNOWLEDGE_ROOT"] = "missing-knowledge"
