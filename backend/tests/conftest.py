"""Test configuration.

Ensures the ``backend`` directory is on ``sys.path`` so ``app.*``
imports resolve when pytest is invoked from any working directory.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
