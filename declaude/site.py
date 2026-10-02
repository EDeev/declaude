"""Builds the whole static site: assets, index, project and conversation pages."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from importlib.resources import files

from .html import HtmlBuilder
from .loader import DataLoader, MappingManager
from .markdown import MarkdownRenderer

CSS = files("declaude").joinpath("assets/style.css").read_text(encoding="utf-8")
JS = files("declaude").joinpath("assets/app.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# SiteBuilder
# ---------------------------------------------------------------------------

class SiteBuilder:
    """Orchestrates generating the full static site."""

    def __init__(self, output_dir: Path, loader: DataLoader, mapping: MappingManager):
        self.out = output_dir
        self.meta_file = output_dir / "_meta.json"
        self.loader = loader
        self.mapping = mapping
        self.md = MarkdownRenderer()
        self.builder = HtmlBuilder(self.md)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def build_assets(self) -> None:
        assets = self.out / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        (assets / "style.css").write_text(CSS, encoding="utf-8")
        (assets / "app.js").write_text(JS, encoding="utf-8")

    def build_all(self, new_uuids: Optional[set] = None) -> None:
        new_uuids = new_uuids or set()
        print("  Building assets...")
        self.build_assets()

        print("  Building index...")
        meta = self._load_meta()
        html = self.builder.build_index(self.loader, self.mapping, meta, new_uuids)
        self._write(self.out / "index.html", html)

        print("  Building all_conversations...")
        html = self.builder.build_all_conversations(self.loader, self.mapping, new_uuids)
        self._write(self.out / "all_conversations.html", html)

        print(f"  Building {len(self.loader.projects)} project pages...")
        for proj in self.loader.projects.values():
            pid = proj.get("uuid","")
            html = self.builder.build_project_page(proj, self.loader, self.mapping)
            self._write(self.out / "projects" / pid / "index.html", html)

        print(f"  Building {len(self.loader.conversations)} conversation pages...")
        for i, conv in enumerate(self.loader.conversations, 1):
            cid = conv.get("uuid","")
            html = self.builder.build_conversation_page(conv, self.loader, self.mapping)
            self._write(self.out / "conversations" / f"{cid}.html", html)
            if i % 100 == 0:
                print(f"    {i}/{len(self.loader.conversations)}")

        self._save_meta()
        print(f"  Done. Archive at: {self.out / 'index.html'}")

    def build_remap(self) -> None:
        """Regenerate only index, all_conversations, and project pages (fast after mapping change)."""
        print("  Rebuilding index and project pages...")
        meta = self._load_meta()
        new_uuids: set = set()

        html = self.builder.build_index(self.loader, self.mapping, meta, new_uuids)
        self._write(self.out / "index.html", html)

        html = self.builder.build_all_conversations(self.loader, self.mapping, new_uuids)
        self._write(self.out / "all_conversations.html", html)

        for proj in self.loader.projects.values():
            pid = proj.get("uuid","")
            html = self.builder.build_project_page(proj, self.loader, self.mapping)
            self._write(self.out / "projects" / pid / "index.html", html)

        print("  Remap complete.")

    def build_update(self, new_loader: DataLoader) -> None:
        """Merge new backup data, regenerate changed pages only."""
        existing_uuids = {c.get("uuid","") for c in self.loader.conversations}
        new_uuids = set()
        changed_uuids = set()

        for conv in new_loader.conversations:
            cid = conv.get("uuid","")
            if cid not in existing_uuids:
                new_uuids.add(cid)
            else:
                # Find old version and compare updated_at
                old = next((c for c in self.loader.conversations if c.get("uuid") == cid), None)
                if old and old.get("updated_at","") != conv.get("updated_at",""):
                    changed_uuids.add(cid)

        print(f"  New conversations: {len(new_uuids)}, Changed: {len(changed_uuids)}")

        # Replace loader data with new
        self.loader.conversations = new_loader.conversations
        self.loader.projects = new_loader.projects
        self.loader.user = new_loader.user

        # Regenerate only new/changed conversation pages
        conv_map = {c.get("uuid",""): c for c in self.loader.conversations}
        to_regen = new_uuids | changed_uuids
        for cid in to_regen:
            if cid in conv_map:
                conv = conv_map[cid]
                html = self.builder.build_conversation_page(conv, self.loader, self.mapping)
                self._write(self.out / "conversations" / f"{cid}.html", html)

        # Rebuild index pages
        meta = self._load_meta()
        html = self.builder.build_index(self.loader, self.mapping, meta, new_uuids)
        self._write(self.out / "index.html", html)

        html = self.builder.build_all_conversations(self.loader, self.mapping, new_uuids)
        self._write(self.out / "all_conversations.html", html)

        # Rebuild affected project pages
        affected_projects: set = set()
        for cid in to_regen:
            pid = self.mapping.get_project(cid)
            if pid:
                affected_projects.add(pid)
        for pid in affected_projects:
            if pid in self.loader.projects:
                proj = self.loader.projects[pid]
                html = self.builder.build_project_page(proj, self.loader, self.mapping)
                self._write(self.out / "projects" / pid / "index.html", html)

        # Rebuild all project pages (new projects may have appeared)
        for proj in self.loader.projects.values():
            pid = proj.get("uuid","")
            if pid not in affected_projects:
                html = self.builder.build_project_page(proj, self.loader, self.mapping)
                self._write(self.out / "projects" / pid / "index.html", html)

        self.build_assets()
        self._save_meta()
        print(f"  Update complete. {len(new_uuids)} new, {len(changed_uuids)} changed.")

    def _load_meta(self) -> Dict:
        if self.meta_file.exists():
            try:
                with open(self.meta_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_meta(self) -> None:
        meta = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "conversation_uuids": [c.get("uuid","") for c in self.loader.conversations],
            "project_uuids": list(self.loader.projects.keys()),
        }
        self.meta_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
