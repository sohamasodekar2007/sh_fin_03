from __future__ import annotations

import os
import tempfile
from pathlib import Path


WORKSPACE_TMP = Path(__file__).resolve().parents[1] / ".tmp" / "pytest"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)

tempfile.tempdir = str(WORKSPACE_TMP)
os.environ["TMP"] = str(WORKSPACE_TMP)
os.environ["TEMP"] = str(WORKSPACE_TMP)

os.environ.pop("AWS_PROFILE", None)
os.environ.pop("AWS_DEFAULT_PROFILE", None)
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
