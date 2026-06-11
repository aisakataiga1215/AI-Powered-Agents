"""Test configuration.

Ensures the ``backend`` directory is on ``sys.path`` so ``app.*``
imports resolve when pytest is invoked from any working directory.
"""

import sys
import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Unit tests must not try to reach LangSmith. The project-level .env may enable
# tracing for demos, so test startup pins all tracing env vars off before app
# modules import settings or LangChain clients.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ.pop("LANGSMITH_API_KEY", None)
os.environ.pop("LANGCHAIN_API_KEY", None)
