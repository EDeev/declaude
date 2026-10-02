"""Loading a Claude.ai data export and the conversation → project mapping."""
from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

BACKUP_CONVERSATIONS = "conversations.json"
BACKUP_USERS = "users.json"
BACKUP_PROJECTS_DIR = "projects"


# ---------------------------------------------------------------------------
# DataLoader
# ---------------------------------------------------------------------------

class DataLoader:
    """Loads and validates Claude backup data from a directory."""

    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.conversations: List[Dict] = []
        self.projects: Dict[str, Dict] = {}   # uuid → project
        self.user: Dict = {}

    def load(self) -> None:
        self._load_user()
        self._load_projects()
        self._load_conversations()

    def _load_user(self) -> None:
        path = self.source_dir / BACKUP_USERS
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                self.user = data[0]
            elif isinstance(data, dict):
                self.user = data
        except Exception as e:
            print(f"  Warning: could not load users.json: {e}")

    def _load_projects(self) -> None:
        projects_dir = self.source_dir / BACKUP_PROJECTS_DIR
        if not projects_dir.is_dir():
            print(f"  Warning: projects/ directory not found in {self.source_dir}")
            return
        for json_file in projects_dir.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "uuid" in data:
                    self.projects[data["uuid"]] = data
            except Exception as e:
                print(f"  Warning: could not load {json_file.name}: {e}")
        print(f"  Loaded {len(self.projects)} projects")

    def _load_conversations(self) -> None:
        path = self.source_dir / BACKUP_CONVERSATIONS
        if not path.exists():
            print(f"Error: {path} not found.")
            sys.exit(1)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                print("Error: conversations.json is not a JSON array.")
                sys.exit(1)
            self.conversations = data
        except Exception as e:
            print(f"Error loading conversations.json: {e}")
            sys.exit(1)
        print(f"  Loaded {len(self.conversations)} conversations")


# ---------------------------------------------------------------------------
# MappingManager
# ---------------------------------------------------------------------------

class MappingManager:
    """Manages conv_uuid → project_uuid mapping with persistence."""

    def __init__(self, mapping_path: Path):
        self.path = mapping_path
        self.data: Dict[str, str] = {}   # conv_uuid → project_uuid

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self.data = {str(k): str(v) for k, v in raw.items()}
        except Exception as e:
            print(f"  Warning: could not load mapping.json: {e}")

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def assign(self, conv_uuid: str, project_uuid: str) -> None:
        self.data[conv_uuid] = project_uuid

    def get_project(self, conv_uuid: str) -> Optional[str]:
        return self.data.get(conv_uuid)

    def conversations_for_project(self, project_uuid: str) -> List[str]:
        return [c for c, p in self.data.items() if p == project_uuid]

    def merge_from_browser(self, browser_export: Dict[str, str]) -> int:
        """Merge browser localStorage export into mapping. Returns count of new entries."""
        added = 0
        for conv_uuid, proj_uuid in browser_export.items():
            if conv_uuid not in self.data:
                self.data[conv_uuid] = proj_uuid
                added += 1
        return added


# ---------------------------------------------------------------------------
# Zip extraction helper
# ---------------------------------------------------------------------------

def extract_zip(zip_path: Path, target_dir: Path) -> Path:
    """Extract zip archive to target_dir, return the root directory inside."""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    # If zip has a single root folder, use that
    children = list(target_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return target_dir
