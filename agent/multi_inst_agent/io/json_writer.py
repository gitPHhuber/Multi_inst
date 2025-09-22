"""Report writer for diagnostic JSON outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from ..core.utils import ensure_dir, make_uid_name


class ReportWriter:
    def __init__(self, out_dir: str) -> None:
        self.out_dir = Path(out_dir)
        ensure_dir(str(self.out_dir))
        self.summary: List[Dict] = []
        self.defect_counter = 1

    def write_report(self, uid: str | None, report: Dict) -> Path:
        filename = make_uid_name(uid, self.defect_counter)
        if filename.startswith("DEFECT"):
            self.defect_counter += 1
        path = self.out_dir / filename
        with path.open("w", encoding="utf-8") as fp:
            json.dump(report, fp, indent=2)
        self._fix_permissions(path)
        self.summary.append(report)
        return path

    def write_summary(self) -> Path:
        path = self.out_dir / "_summary.json"
        with path.open("w", encoding="utf-8") as fp:
            json.dump(self.summary, fp, indent=2)
        self._fix_permissions(path)
        return path

    def _fix_permissions(self, path: Path) -> None:
        sudo_uid = os.environ.get("SUDO_UID")
        sudo_gid = os.environ.get("SUDO_GID")
        if sudo_uid and sudo_gid:
            os.chown(path, int(sudo_uid), int(sudo_gid))
        path.chmod(0o664)
        self.out_dir.chmod(0o775)
