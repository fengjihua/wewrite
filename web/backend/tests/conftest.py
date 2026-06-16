import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]          # web/backend
REPO = BACKEND.parents[1]                               # 仓库根
for p in (str(BACKEND), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)
