"""HTML page templates for the archive."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .loader import DataLoader, MappingManager
from .markdown import MarkdownRenderer


# ---------------------------------------------------------------------------
# HtmlBuilder — page templates
# ---------------------------------------------------------------------------

class HtmlBuilder:
    """Builds complete HTML pages as strings."""

    def __init__(self, md: MarkdownRenderer):
        self.md = md

    # --- Shared helpers --------------------------------------------------- #

    def _page(self, title: str, body: str, depth: int = 0,
              extra_head: str = "", conv_assign_html: str = "") -> str:
        root = "../" * depth
        return f"""<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{self._esc(title)} — Claude Archive</title>
  <link rel="stylesheet" href="{root}assets/style.css">
  {extra_head}
</head>
<body>
  {self._topbar(root, conv_assign_html)}
  <div class="page-wrapper">
    {body}
  </div>
  <script src="{root}assets/app.js"></script>
</body>
</html>"""

    def _topbar(self, root: str, conv_assign_html: str = "") -> str:
        # conv_assign_html is injected right after the nav links, separated by a visual divider
        assign_block = (
            f'<div class="topbar-divider"></div>{conv_assign_html}'
            if conv_assign_html else ""
        )
        return f"""<header class="topbar">
  <a class="topbar-logo" href="{root}index.html">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
    </svg>
    Claude Archive
  </a>
  <nav class="topbar-nav">
    <a href="{root}all_conversations.html"><span data-lang="ru" class="lang-visible">Все чаты</span><span data-lang="en">All chats</span></a>
    <a href="{root}index.html#projects"><span data-lang="ru" class="lang-visible">Проекты</span><span data-lang="en">Projects</span></a>
    {assign_block}
  </nav>
  <div class="topbar-actions">
    <div class="lang-toggle">
      <button class="lang-btn active" id="langRu" onclick="setLang('ru')">RU</button>
      <button class="lang-btn" id="langEn" onclick="setLang('en')">EN</button>
    </div>
    <button class="icon-btn" id="themeToggle" title="Переключить тему" onclick="toggleTheme()">
      <svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
      </svg>
      <svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none">
        <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/>
        <line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/>
        <line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
      </svg>
    </button>
  </div>
</header>"""

    def _esc(self, text) -> str:
        if text is None:
            return ""
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    # Breadcrumb label translations for fixed UI strings
    _BC_I18N: Dict[str, Tuple[str, str]] = {
        "Главная":    ("Главная",    "Home"),
        "Все чаты":  ("Все чаты",  "All chats"),
        "Проекты":   ("Проекты",   "Projects"),
        "Проект":    ("Проект",    "Project"),
    }

    def _breadcrumbs(self, crumbs: List[Tuple[str, Optional[str]]]) -> str:
        parts = []
        for label, href in crumbs:
            if label in self._BC_I18N:
                ru, en = self._BC_I18N[label]
                inner = (
                    f'<span data-lang="ru" class="lang-visible">{self._esc(ru)}</span>'
                    f'<span data-lang="en">{self._esc(en)}</span>'
                )
            else:
                inner = self._esc(label)
            if href:
                parts.append(f'<a href="{href}">{inner}</a>')
            else:
                parts.append(f'<span>{inner}</span>')
        return '<nav class="breadcrumbs">' + '<span class="bc-sep">›</span>'.join(parts) + '</nav>'

    def _format_date(self, iso: str, short: bool = False) -> str:
        if not iso:
            return "—"
        try:
            if iso.endswith("Z"):
                iso = iso[:-1] + "+00:00"
            dt = datetime.fromisoformat(iso)
            if short:
                return dt.strftime("%d.%m.%Y")
            return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return iso

    def _conv_display_name(self, conv: Dict) -> str:
        name = conv.get("name", "").strip()
        if name:
            return name
        msgs = conv.get("chat_messages", [])
        for msg in msgs:
            if msg.get("sender") == "human":
                text = msg.get("text", "")
                if not text:
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            break
                if text:
                    clean = re.sub(r"\s+", " ", text).strip()
                    return clean[:60] + ("..." if len(clean) > 60 else "")
        uid = conv.get("uuid", "")
        return f"Чат {uid[-8:]}" if uid else "Без названия"

    def _conv_preview(self, conv: Dict, max_len: int = 120) -> str:
        msgs = conv.get("chat_messages", [])
        for msg in msgs:
            if msg.get("sender") == "human":
                text = msg.get("text", "")
                if not text:
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            break
                if text:
                    clean = re.sub(r"```[\s\S]*?```", "[код]", text)
                    clean = re.sub(r"`[^`]+`", "[код]", clean)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    return clean[:max_len] + ("..." if len(clean) > max_len else "")
        return ""

    # --- Index page ------------------------------------------------------- #

    def build_index(self, loader: DataLoader, mapping: MappingManager,
                    meta: Dict, new_uuids: set) -> str:
        user = loader.user
        convs = loader.conversations
        projects = loader.projects

        total_msgs = sum(len(c.get("chat_messages", [])) for c in convs)
        gen_time = datetime.now().strftime("%d.%m.%Y %H:%M")

        # stats strip
        stats_html = f"""<div class="stats-strip">
  <div class="stat-item"><span class="stat-num">{len(convs)}</span><span class="stat-lbl"><span data-lang="ru" class="lang-visible">чатов</span><span data-lang="en">chats</span></span></div>
  <div class="stat-item"><span class="stat-num">{total_msgs}</span><span class="stat-lbl"><span data-lang="ru" class="lang-visible">сообщений</span><span data-lang="en">messages</span></span></div>
  <div class="stat-item"><span class="stat-num">{len(projects)}</span><span class="stat-lbl"><span data-lang="ru" class="lang-visible">проектов</span><span data-lang="en">projects</span></span></div>
  <div class="stat-item"><span class="stat-num">{len(mapping.data)}</span><span class="stat-lbl"><span data-lang="ru" class="lang-visible">привязано</span><span data-lang="en">mapped</span></span></div>
</div>"""

        # user info
        user_html = ""
        if user:
            user_html = f"""<div class="card user-card">
  <div class="user-avatar">{self._esc(user.get('full_name','?')[:1])}</div>
  <div>
    <div class="user-name">{self._esc(user.get('full_name','Unknown'))}</div>
    <div class="user-email">{self._esc(user.get('email_address',''))}</div>
  </div>
</div>"""

        # projects grid
        sorted_projects = sorted(projects.values(), key=lambda p: p.get("updated_at",""), reverse=True)
        project_cards = ""
        for proj in sorted_projects:
            pid = proj.get("uuid","")
            pname = self._esc(proj.get("name","Без названия"))
            pdesc = self._esc(proj.get("description","") or "")
            pdocs = len(proj.get("docs",[]))
            pcnt = len(mapping.conversations_for_project(pid))
            pupdated = self._format_date(proj.get("updated_at",""), short=True)
            project_cards += f"""<a class="project-card" href="projects/{pid}/index.html">
  <div class="pc-name">{pname}</div>
  {f'<div class="pc-desc">{pdesc}</div>' if pdesc else ''}
  <div class="pc-meta">
    <span>{pdocs} doc{'s' if pdocs!=1 else ''}</span>
    <span>{pcnt} чат{'а' if pcnt in(2,3,4) else 'ов' if pcnt!=1 else ''}</span>
    <span>{pupdated}</span>
  </div>
</a>"""

        # recent conversations
        recent = sorted(convs, key=lambda c: c.get("updated_at",""), reverse=True)[:15]
        recent_rows = ""
        for conv in recent:
            cid = conv.get("uuid","")
            cname = self._esc(self._conv_display_name(conv))
            cupdated = self._format_date(conv.get("updated_at",""))
            cmsg = len(conv.get("chat_messages",[]))
            cproj_uuid = mapping.get_project(cid)
            cproj_name = ""
            if cproj_uuid and cproj_uuid in loader.projects:
                cproj_name = self._esc(loader.projects[cproj_uuid].get("name",""))
            is_new = cid in new_uuids
            new_badge = '<span class="badge badge-new">new</span>' if is_new else ""
            proj_badge = f'<span class="badge badge-proj">{cproj_name}</span>' if cproj_name else ""
            recent_rows += f"""<a class="conv-row" href="conversations/{cid}.html">
  <span class="conv-row-name">{cname} {new_badge} {proj_badge}</span>
  <span class="conv-row-meta">{cmsg} сообщ. · {cupdated}</span>
</a>"""

        # mapping sync panel
        sync_panel = """<div class="sync-panel card" id="syncPanel">
  <div class="sync-panel-header">
    <strong><span data-lang="ru" class="lang-visible">Синхронизация маппинга</span><span data-lang="en">Mapping sync</span></strong>
    <span class="sync-status" id="syncStatus"></span>
  </div>
  <p class="sync-desc">
    <span data-lang="ru" class="lang-visible">Привязки чатов к проектам, сделанные в браузере, хранятся в localStorage.
    Нажмите «Экспорт», скачайте файл, положите рядом со скриптом как <code>mapping.json</code>,
    затем запустите <code>python declaude.py --remap</code>.</span>
    <span data-lang="en">Browser-side project assignments are stored in localStorage.
    Click Export, save the file next to the script as <code>mapping.json</code>,
    then run <code>python declaude.py --remap</code>.</span>
  </p>
  <div class="sync-actions">
    <button class="btn btn-primary" onclick="exportMapping()">
      <span data-lang="ru" class="lang-visible">Экспорт mapping.json</span>
      <span data-lang="en">Export mapping.json</span>
    </button>
    <button class="btn" onclick="clearBrowserMapping()">
      <span data-lang="ru" class="lang-visible">Сбросить браузерный маппинг</span>
      <span data-lang="en">Reset browser mapping</span>
    </button>
  </div>
</div>"""

        body = f"""<main class="main-content">
  {user_html}
  {stats_html}
  <p class="gen-note"><span data-lang="ru" class="lang-visible">Архив сгенерирован:</span><span data-lang="en">Archive generated:</span> {gen_time}</p>

  <section id="projects">
    <h2 class="section-title"><span data-lang="ru" class="lang-visible">Проекты</span><span data-lang="en">Projects</span></h2>
    <div class="projects-grid">{project_cards if project_cards else '<p class="muted"><span data-lang="ru" class="lang-visible">Нет проектов в архиве.</span><span data-lang="en">No projects in archive.</span></p>'}</div>
  </section>

  <section id="recent">
    <h2 class="section-title">
      <span data-lang="ru" class="lang-visible">Последние чаты</span><span data-lang="en">Recent chats</span>
      <a href="all_conversations.html" class="section-link"><span data-lang="ru" class="lang-visible">Все →</span><span data-lang="en">All →</span></a>
    </h2>
    <div class="conv-list">{recent_rows}</div>
  </section>

  <section id="sync">
    <h2 class="section-title"><span data-lang="ru" class="lang-visible">Синхронизация маппинга</span><span data-lang="en">Mapping sync</span></h2>
    {sync_panel}
  </section>
</main>"""

        return self._page("Архив", body, depth=0)

    # --- All conversations page ------------------------------------------- #

    def build_all_conversations(self, loader: DataLoader, mapping: MappingManager,
                                new_uuids: set) -> str:
        convs = loader.conversations
        projects = loader.projects

        sorted_convs = sorted(convs, key=lambda c: c.get("updated_at",""), reverse=True)

        # Build project filter options (data-ru/data-en for JS i18n since <option> can't have child spans)
        proj_options = '<option value="" data-ru="Все проекты" data-en="All projects">Все проекты</option>'
        proj_options += '<option value="__none__" data-ru="Без проекта" data-en="No project">Без проекта</option>'
        for proj in sorted(projects.values(), key=lambda p: p.get("name","")):
            pid = proj.get("uuid","")
            pname = self._esc(proj.get("name",""))
            proj_options += f'<option value="{pid}">{pname}</option>'

        rows_html = ""
        for conv in sorted_convs:
            cid = conv.get("uuid","")
            cname = self._esc(self._conv_display_name(conv))
            cpreview = self._esc(self._conv_preview(conv))
            cupdated = self._format_date(conv.get("updated_at",""))
            ccreated = self._format_date(conv.get("created_at",""), short=True)
            cmsg = len(conv.get("chat_messages",[]))
            cproj_uuid = mapping.get_project(cid) or ""
            cproj_name = ""
            if cproj_uuid and cproj_uuid in projects:
                cproj_name = self._esc(projects[cproj_uuid].get("name",""))
            is_new = cid in new_uuids
            new_badge = '<span class="badge badge-new">new</span>' if is_new else ""
            proj_badge = f'<span class="badge badge-proj">{cproj_name}</span>' if cproj_name else ""

            rows_html += f"""<a class="conv-card"
  href="conversations/{cid}.html"
  data-name="{cname.lower()}"
  data-preview="{cpreview.lower()}"
  data-proj="{cproj_uuid}"
  data-updated="{conv.get('updated_at','')}"
  data-created="{conv.get('created_at','')}"
  data-msgs="{cmsg}">
  <div class="cc-top">
    <span class="cc-name">{cname}</span>
    <span class="cc-badges">{new_badge}{proj_badge}</span>
  </div>
  {f'<div class="cc-preview">{cpreview}</div>' if cpreview else ''}
  <div class="cc-meta">{cmsg} <span data-lang="ru" class="lang-visible">сообщ.</span><span data-lang="en">msg</span> · {cupdated} · <span data-lang="ru" class="lang-visible">создан</span><span data-lang="en">created</span> {ccreated}</div>
</a>"""

        body = f"""<main class="main-content">
  {self._breadcrumbs([("Главная","index.html"),("Все чаты",None)])}
  <h1>
    <span data-lang="ru" class="lang-visible">Все чаты</span>
    <span data-lang="en">All chats</span>
    <span class="count-badge">{len(convs)}</span>
  </h1>

  <div class="filters-bar">
    <input type="search" id="searchInput"
      data-placeholder-ru="Поиск по названию или тексту..."
      data-placeholder-en="Search by title or text..."
      placeholder="Поиск по названию или тексту..."
      class="search-input" oninput="filterConvs()">
    <select id="projFilter" class="select-input" onchange="filterConvs()">
      {proj_options}
    </select>
    <select id="sortSelect" class="select-input" onchange="filterConvs()">
      <option value="updated" data-ru="По дате обновления" data-en="By update date">По дате обновления</option>
      <option value="created" data-ru="По дате создания" data-en="By creation date">По дате создания</option>
      <option value="msgs" data-ru="По числу сообщений" data-en="By message count">По числу сообщений</option>
    </select>
    <span id="countLabel" class="filter-count"></span>
  </div>

  <div class="conv-grid" id="convGrid">
    {rows_html}
  </div>
</main>"""

        return self._page("Все чаты", body, depth=0,
                          extra_head='<script>window.PAGE_TYPE="all_convs";</script>')

    # --- Project page ----------------------------------------------------- #

    def build_project_page(self, project: Dict, loader: DataLoader,
                           mapping: MappingManager) -> str:
        pid = project.get("uuid","")
        pname = project.get("name","Без названия")
        pdesc = project.get("description","") or ""
        pcreated = self._format_date(project.get("created_at",""))
        pupdated = self._format_date(project.get("updated_at",""))
        pprompt = project.get("prompt_template","") or ""
        docs = project.get("docs",[])

        # Documents section
        docs_html = ""
        if docs:
            for doc in docs:
                dname = self._esc(doc.get("filename","Без названия"))
                dcreated = self._format_date(doc.get("created_at",""))
                dcontent = doc.get("content","") or ""
                doc_rendered = self.md.render(dcontent) if dcontent else "<p class='muted'>Нет содержимого.</p>"
                docs_html += f"""<details class="doc-block">
  <summary class="doc-summary">
    <span class="doc-icon">📄</span>
    <span class="doc-name">{dname}</span>
    <span class="doc-date muted">{dcreated}</span>
  </summary>
  <div class="doc-content">{doc_rendered}</div>
</details>"""
        else:
            docs_html = '<p class="muted">Нет документов в этом проекте.</p>'

        # Prompt template
        prompt_html = ""
        if pprompt:
            prompt_rendered = self.md.render(pprompt)
            prompt_html = f"""<section class="card">
  <h2>Системный промпт</h2>
  <div class="prompt-content">{prompt_rendered}</div>
</section>"""

        # Conversations
        conv_uuids = mapping.conversations_for_project(pid)
        conv_map = {c.get("uuid",""): c for c in loader.conversations}
        proj_convs = [conv_map[u] for u in conv_uuids if u in conv_map]
        proj_convs.sort(key=lambda c: c.get("updated_at",""), reverse=True)

        conv_rows = ""
        for conv in proj_convs:
            cid = conv.get("uuid","")
            cname = self._esc(self._conv_display_name(conv))
            cpreview = self._esc(self._conv_preview(conv))
            cupdated = self._format_date(conv.get("updated_at",""))
            cmsg = len(conv.get("chat_messages",[]))
            conv_rows += f"""<a class="conv-row" href="../../conversations/{cid}.html">
  <span class="conv-row-name">{cname}</span>
  <span class="conv-row-meta">{cmsg} сообщ. · {cupdated}</span>
</a>
{f'<div class="conv-row-preview">{cpreview}</div>' if cpreview else ''}"""

        convs_section = f"""<section>
  <h2>Привязанные чаты <span class="count-badge">{len(proj_convs)}</span></h2>
  {f'<div class="conv-list">{conv_rows}</div>' if proj_convs else '<p class="muted">Нет привязанных чатов. Откройте чат и нажмите «Привязать к проекту».</p>'}
</section>"""

        body = f"""<main class="main-content">
  {self._breadcrumbs([("Главная","../../index.html"),("Проекты","../../index.html#projects"),(pname,None)])}
  <h1>{self._esc(pname)}</h1>

  <div class="card meta-card">
    {f'<p class="project-desc">{self._esc(pdesc)}</p>' if pdesc else ''}
    <div class="meta-grid">
      <span class="meta-lbl">Создан</span><span>{pcreated}</span>
      <span class="meta-lbl">Обновлён</span><span>{pupdated}</span>
      <span class="meta-lbl">Документов</span><span>{len(docs)}</span>
      <span class="meta-lbl">Чатов</span><span>{len(proj_convs)}</span>
    </div>
  </div>

  {prompt_html}

  <section>
    <h2>Документы <span class="count-badge">{len(docs)}</span></h2>
    <div class="docs-list">{docs_html}</div>
  </section>

  {convs_section}
</main>"""

        return self._page(pname, body, depth=2)

    # --- Conversation page ------------------------------------------------ #

    def build_conversation_page(self, conv: Dict, loader: DataLoader,
                                mapping: MappingManager) -> str:
        cid = conv.get("uuid","")
        cname = self._conv_display_name(conv)
        ccreated = self._format_date(conv.get("created_at",""))
        cupdated = self._format_date(conv.get("updated_at",""))
        messages = conv.get("chat_messages",[])

        # Sort messages by created_at
        try:
            messages = sorted(messages, key=lambda m: m.get("created_at",""))
        except Exception:
            pass

        # Current project assignment
        cproj_uuid = mapping.get_project(cid) or ""

        # Project assignment widget — goes into topbar
        # Note: <option> can't contain HTML tags, so i18n for the placeholder is done via JS (data-i18n attr)
        proj_options_html = '<option value="" data-ru="— Не привязан —" data-en="— Not assigned —">— Не привязан —</option>'
        for proj in sorted(loader.projects.values(), key=lambda p: p.get("name","")):
            pid2 = proj.get("uuid","")
            pn = self._esc(proj.get("name",""))
            selected = 'selected' if pid2 == cproj_uuid else ''
            proj_options_html += f'<option value="{pid2}" {selected}>{pn}</option>'

        open_proj_link = (
            f'<a class="topbar-assign-link" id="assignProjLink" href="../projects/{cproj_uuid}/index.html">'
            f'<span data-lang="ru" class="lang-visible">Открыть →</span>'
            f'<span data-lang="en">Open →</span>'
            f'</a>'
            if cproj_uuid else
            '<a class="topbar-assign-link" id="assignProjLink" href="#" style="display:none">'
            '<span data-lang="ru" class="lang-visible">Открыть →</span>'
            '<span data-lang="en">Open →</span>'
            '</a>'
        )

        conv_assign_html = f"""<div class="topbar-assign">
  <span class="topbar-assign-label">
    <span data-lang="ru" class="lang-visible">Проект:</span>
    <span data-lang="en">Project:</span>
  </span>
  <select id="projSelect" class="select-input" onchange="assignProject('{cid}', this.value)">
    {proj_options_html}
  </select>
  {open_proj_link}
</div>"""

        # FAB scroll buttons
        scroll_fabs = """<div class="scroll-fabs" id="scrollFabs">
  <button class="scroll-fab hidden" id="fabTop" onclick="scrollToTop()" title="В начало">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="18 15 12 9 6 15"/>
    </svg>
  </button>
  <button class="scroll-fab" id="fabBottom" onclick="scrollToBottom()" title="В конец">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  </button>
</div>"""

        # Messages
        msgs_html = ""
        for i, msg in enumerate(messages):
            sender = msg.get("sender","unknown")
            ts = self._format_date(msg.get("created_at",""))
            text = msg.get("text","")
            if not text:
                parts = []
                for block in msg.get("content",[]):
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text",""))
                text = "\n".join(parts)

            attachments = msg.get("attachments",[])
            files = msg.get("files",[])

            rendered = self.md.render(text) if text else (
                '<p class="muted">'
                '<span data-lang="ru" class="lang-visible">[нет текста]</span>'
                '<span data-lang="en">[no text]</span>'
                '</p>'
            )

            # Attachments
            attach_html = ""
            for att in attachments:
                fname = self._esc(att.get("file_name","файл"))
                fsize = att.get("file_size",0)
                ftype = self._esc(att.get("file_type","") or "")
                extracted = att.get("extracted_content","") or ""
                size_str = f"{fsize:,}".replace(",", " ") + " б" if fsize else ""
                if extracted:
                    ext_rendered = self.md.render(extracted)
                    attach_html += f"""<details class="attachment">
  <summary class="att-summary">
    <span class="att-icon">📎</span>
    <span class="att-name">{fname}</span>
    {f'<span class="att-meta">{ftype} · {size_str}</span>' if ftype or size_str else ''}
  </summary>
  <div class="att-content">{ext_rendered}</div>
</details>"""
                else:
                    attach_html += f"""<div class="attachment att-badge">
  <span class="att-icon">📎</span>
  <span class="att-name">{fname}</span>
  {f'<span class="att-meta">{ftype} · {size_str}</span>' if ftype or size_str else ''}
</div>"""

            for fobj in files:
                fname = self._esc(fobj.get("file_name","файл"))
                attach_html += f'<div class="attachment att-badge"><span class="att-icon">📁</span> <span class="att-name">{fname}</span></div>'

            is_human = sender == "human"
            role_cls = "msg-human" if is_human else "msg-claude"
            avatar = f"""<div class="msg-avatar {'avatar-human' if is_human else 'avatar-claude'}">
  {'<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>' if is_human else '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'}
</div>"""
            sender_label_html = (
                '<span data-lang="ru" class="lang-visible">Вы</span><span data-lang="en">You</span>'
                if is_human else "Claude"
            )

            msgs_html += f"""<div class="message {role_cls}" id="msg-{i}">
  <div class="msg-meta">
    {avatar}
    <span class="msg-sender">{sender_label_html}</span>
    <span class="msg-ts">{ts}</span>
  </div>
  <div class="msg-body">
    <div class="msg-content">{rendered}</div>
    {f'<div class="msg-attachments">{attach_html}</div>' if attach_html else ''}
  </div>
</div>"""

        body = f"""<main class="main-content conv-page">
  {self._breadcrumbs([("Главная","../index.html"),("Все чаты","../all_conversations.html"),(cname,None)])}
  <h1 class="conv-title">{self._esc(cname)}</h1>
  <div class="conv-meta-bar">
    <span><span data-lang="ru" class="lang-visible">Создан:</span><span data-lang="en">Created:</span> {ccreated}</span>
    <span><span data-lang="ru" class="lang-visible">Обновлён:</span><span data-lang="en">Updated:</span> {cupdated}</span>
    <span>{len(messages)} <span data-lang="ru" class="lang-visible">сообщений</span><span data-lang="en">messages</span></span>
    <span class="conv-uuid muted">ID: {cid}</span>
  </div>

  <div class="messages-container" id="messagesContainer">
    {msgs_html}
  </div>
  {scroll_fabs}
</main>"""

        return self._page(
            cname, body, depth=1,
            extra_head=f'<script>window.CONV_UUID="{cid}";window.PAGE_TYPE="conversation";</script>',
            conv_assign_html=conv_assign_html
        )


