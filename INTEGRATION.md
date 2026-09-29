# Claude Archive Converter — интеграция в FastAPI сайт

## Что нужно сделать

Встроить модуль конвертации Claude-бэкапа в статический HTML-архив как endpoint FastAPI-сайта.

**Пользовательский сценарий:**
1. Пользователь открывает страницу `/tools/claude-archive`
2. Перетаскивает или выбирает zip-файл (скачанный с claude.ai — экспорт данных)
3. Видит прогресс-бар обработки
4. Получает ссылку для скачивания готового zip-архива с HTML-страницами
5. Файл автоматически удаляется с сервера через 10 минут

---

## Ядро конвертера

Файл `declaude.py` уже существует и полностью работоспособен. Его **не нужно переписывать** — нужно только обернуть в веб-слой.

Ключевые классы из `declaude.py`:
- `DataLoader(source_dir)` — загружает `conversations.json`, `projects/*.json`, `users.json`
- `MappingManager(path)` — читает/пишет `mapping.json`
- `SiteBuilder(output_dir, loader, mapping)` — генерирует всё HTML
- `SiteBuilder.build_all()` — запускает полную генерацию

Пример минимального вызова (уже работает локально):
```python
from declaude import DataLoader, MappingManager, SiteBuilder
from pathlib import Path

loader = DataLoader(Path("extracted_backup/"))
loader.load()
mapping = MappingManager(Path("mapping.json"))
mapping.load()
site = SiteBuilder(Path("output/"), loader, mapping)
site.build_all()
```

---

## Структура файлов, которые нужно создать

```
your_project/
├── routers/
│   └── claude_archive.py       # новый роутер FastAPI
├── services/
│   └── claude_converter.py     # бизнес-логика: распаковка, запуск, упаковка
├── templates/
│   └── claude_archive.html     # страница загрузки (Jinja2 или отдельный HTML)
├── static/
│   └── claude_archive.js       # фронтенд: upload, polling, progress bar
└── declaude.py                 # уже существует — НЕ ТРОГАТЬ
```

Подключи роутер в `main.py`:
```python
from routers.claude_archive import router as claude_archive_router
app.include_router(claude_archive_router, prefix="/tools")
```

---

## routers/claude_archive.py

```python
import asyncio
import uuid
import zipfile
import shutil
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["claude-archive"])

# Временная директория для задач
WORK_DIR = Path("/tmp/claude_archive_jobs")
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Хранилище состояний задач в памяти (для prod замени на Redis)
jobs: Dict[str, dict] = {}


@router.get("/claude-archive")
async def page():
    """Страница загрузки — отдаёт HTML."""
    from fastapi.responses import HTMLResponse
    # Если используешь Jinja2, подключи TemplateResponse
    html = Path("templates/claude_archive.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@router.post("/claude-archive/upload")
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Принимает zip-файл, запускает конвертацию в фоне.
    Возвращает job_id для polling статуса.
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Ожидается .zip файл")

    # Ограничение размера: 500 MB
    MAX_SIZE = 500 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, "Файл слишком большой (макс. 500 MB)")

    job_id = str(uuid.uuid4())
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()

    # Сохраняем загруженный zip
    upload_path = job_dir / "upload.zip"
    upload_path.write_bytes(content)

    # Регистрируем задачу
    jobs[job_id] = {"status": "queued", "progress": 0, "error": None}

    # Запускаем конвертацию в фоне
    background_tasks.add_task(run_conversion, job_id, job_dir)

    return JSONResponse({"job_id": job_id})


@router.get("/claude-archive/status/{job_id}")
async def status(job_id: str):
    """Polling endpoint — возвращает статус задачи."""
    if job_id not in jobs:
        raise HTTPException(404, "Задача не найдена")
    return JSONResponse(jobs[job_id])


@router.get("/claude-archive/download/{job_id}")
async def download(job_id: str):
    """Скачать готовый архив."""
    if job_id not in jobs:
        raise HTTPException(404, "Задача не найдена")
    if jobs[job_id]["status"] != "done":
        raise HTTPException(400, "Архив ещё не готов")

    result_zip = WORK_DIR / job_id / "result.zip"
    if not result_zip.exists():
        raise HTTPException(404, "Файл не найден")

    return FileResponse(
        path=str(result_zip),
        media_type="application/zip",
        filename="claude_archive.zip",
        headers={"Content-Disposition": "attachment; filename=claude_archive.zip"}
    )
```

---

## services/claude_converter.py

```python
import asyncio
import zipfile
import shutil
import traceback
from pathlib import Path
from routers.claude_archive import jobs, WORK_DIR


async def run_conversion(job_id: str, job_dir: Path):
    """
    Фоновая задача: распаковать upload.zip, запустить declaude, упаковать результат.
    Обновляет jobs[job_id] по ходу выполнения.
    Удаляет все файлы через 10 минут после завершения.
    """
    try:
        jobs[job_id]["status"] = "extracting"
        jobs[job_id]["progress"] = 5

        # 1. Распаковываем загруженный архив
        extract_dir = job_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(job_dir / "upload.zip", "r") as zf:
            zf.extractall(extract_dir)

        # Если внутри zip есть одна папка — используем её как source
        children = list(extract_dir.iterdir())
        source_dir = children[0] if len(children) == 1 and children[0].is_dir() else extract_dir

        jobs[job_id]["status"] = "loading"
        jobs[job_id]["progress"] = 15

        # 2. Запускаем тяжёлую работу в thread pool (не блокируем event loop)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _build_archive, job_id, source_dir, job_dir)

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        traceback.print_exc()
    finally:
        # Удаляем файлы через 10 минут
        await asyncio.sleep(600)
        shutil.rmtree(job_dir, ignore_errors=True)
        jobs.pop(job_id, None)


def _build_archive(job_id: str, source_dir: Path, job_dir: Path):
    """
    Синхронная часть — выполняется в thread pool.
    Импортируем declaude здесь чтобы не тащить в event loop.
    """
    import sys
    import os
    # declaude.py лежит в корне проекта — добавляем в path если нужно
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from declaude import DataLoader, MappingManager, SiteBuilder

    output_dir = job_dir / "output"
    output_dir.mkdir()

    jobs[job_id]["status"] = "building"
    jobs[job_id]["progress"] = 30

    # Загружаем данные
    loader = DataLoader(source_dir)
    loader.load()

    # Пустой маппинг (пользователь может настроить потом через браузер)
    mapping = MappingManager(job_dir / "mapping.json")
    mapping.load()

    jobs[job_id]["progress"] = 50

    # Генерируем HTML-архив
    site = SiteBuilder(output_dir, loader, mapping)
    site.build_all()

    jobs[job_id]["status"] = "packing"
    jobs[job_id]["progress"] = 85

    # Упаковываем результат
    result_zip = job_dir / "result.zip"
    _zip_directory(output_dir, result_zip)

    jobs[job_id]["status"] = "done"
    jobs[job_id]["progress"] = 100


def _zip_directory(source_dir: Path, output_path: Path):
    """Рекурсивно запаковывает директорию в zip с относительными путями."""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)
```

---

## templates/claude_archive.html

Минимальная страница с drag-and-drop загрузкой и прогресс-баром. Адаптируй под свою систему шаблонов (Jinja2, etc.) и дизайн сайта.

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Claude Archive Converter</title>
  <style>
    /* Подключи свои глобальные стили, это только специфика виджета */
    .converter-box {
      max-width: 560px;
      margin: 3rem auto;
      padding: 2rem;
      border: 1px solid var(--border, #383838);
      border-radius: 12px;
      background: var(--bg2, #242424);
      font-family: inherit;
    }
    .drop-zone {
      border: 2px dashed var(--border, #444);
      border-radius: 8px;
      padding: 3rem 1rem;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .drop-zone.drag-over { border-color: #d97706; background: rgba(217,119,6,0.05); }
    .drop-zone input[type=file] { display: none; }
    .progress-bar-wrap {
      background: var(--bg3, #2e2e2e);
      border-radius: 6px;
      height: 8px;
      overflow: hidden;
      margin: 1rem 0;
    }
    .progress-bar-fill {
      height: 100%;
      background: #d97706;
      border-radius: 6px;
      transition: width 0.3s;
      width: 0%;
    }
    .status-msg { font-size: 0.9rem; color: #a0a0a0; margin: 0.5rem 0; }
    .btn-download {
      display: inline-block;
      padding: 0.6rem 1.4rem;
      background: #d97706;
      color: #fff;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 600;
      margin-top: 1rem;
    }
    .error-msg { color: #f87171; font-size: 0.9rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <div class="converter-box">
    <h2>Claude Archive Converter</h2>
    <p style="color:#a0a0a0; font-size:0.9rem; margin-bottom:1.5rem;">
      Загрузите zip-файл экспорта данных Claude (Settings → Privacy → Export data).
      Вы получите красивый HTML-архив всех ваших чатов и проектов.
    </p>

    <div class="drop-zone" id="dropZone">
      <input type="file" id="fileInput" accept=".zip">
      <div id="dropLabel">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="1.5" style="margin-bottom:0.75rem">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <div>Перетащите .zip сюда или <strong style="color:#d97706">выберите файл</strong></div>
        <div style="font-size:0.8rem; color:#666; margin-top:0.4rem">Максимум 500 MB</div>
      </div>
    </div>

    <div id="progressSection" style="display:none">
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="progressFill"></div></div>
      <div class="status-msg" id="statusMsg">Загрузка...</div>
    </div>

    <div id="errorSection" style="display:none">
      <div class="error-msg" id="errorMsg"></div>
      <button onclick="resetForm()" style="margin-top:0.5rem; cursor:pointer">Попробовать ещё раз</button>
    </div>

    <div id="doneSection" style="display:none">
      <div style="color:#4ade80; margin-bottom:0.5rem">✓ Готово! Архив сформирован.</div>
      <a class="btn-download" id="downloadLink" href="#">Скачать claude_archive.zip</a>
      <div style="font-size:0.75rem; color:#666; margin-top:0.5rem">Файл будет удалён с сервера через 10 минут</div>
    </div>
  </div>

  <script src="/static/claude_archive.js"></script>
</body>
</html>
```

---

## static/claude_archive.js

```javascript
const BASE = "/tools/claude-archive";

// Drag & drop
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

function handleFile(file) {
  if (!file.name.endsWith(".zip")) {
    showError("Ожидается файл .zip");
    return;
  }
  uploadFile(file);
}

function uploadFile(file) {
  showProgress(5, "Загрузка файла на сервер...");

  const formData = new FormData();
  formData.append("file", file);

  fetch(`${BASE}/upload`, { method: "POST", body: formData })
    .then((r) => {
      if (!r.ok) return r.json().then((d) => { throw new Error(d.detail || "Ошибка загрузки"); });
      return r.json();
    })
    .then((data) => pollStatus(data.job_id))
    .catch((err) => showError(err.message));
}

let pollTimer = null;

function pollStatus(jobId) {
  const STATUS_LABELS = {
    queued:     "В очереди...",
    extracting: "Распаковка архива...",
    loading:    "Загрузка данных...",
    building:   "Генерация HTML-страниц...",
    packing:    "Упаковка результата...",
    done:       "Готово!",
    error:      "Ошибка",
  };

  fetch(`${BASE}/status/${jobId}`)
    .then((r) => r.json())
    .then((data) => {
      const label = STATUS_LABELS[data.status] || data.status;
      showProgress(data.progress || 0, label);

      if (data.status === "done") {
        showDone(jobId);
      } else if (data.status === "error") {
        showError(data.error || "Неизвестная ошибка");
      } else {
        // Продолжаем polling каждые 1.5 секунды
        pollTimer = setTimeout(() => pollStatus(jobId), 1500);
      }
    })
    .catch((err) => showError("Ошибка polling: " + err.message));
}

// UI helpers
function showProgress(pct, msg) {
  document.getElementById("dropZone").style.display = "none";
  document.getElementById("progressSection").style.display = "block";
  document.getElementById("errorSection").style.display = "none";
  document.getElementById("doneSection").style.display = "none";
  document.getElementById("progressFill").style.width = pct + "%";
  document.getElementById("statusMsg").textContent = msg;
}

function showDone(jobId) {
  document.getElementById("progressSection").style.display = "none";
  document.getElementById("doneSection").style.display = "block";
  document.getElementById("downloadLink").href = `${BASE}/download/${jobId}`;
}

function showError(msg) {
  clearTimeout(pollTimer);
  document.getElementById("progressSection").style.display = "none";
  document.getElementById("dropZone").style.display = "block";
  document.getElementById("errorSection").style.display = "block";
  document.getElementById("errorMsg").textContent = msg;
}

function resetForm() {
  document.getElementById("errorSection").style.display = "none";
  document.getElementById("doneSection").style.display = "none";
  document.getElementById("dropZone").style.display = "block";
  document.getElementById("progressFill").style.width = "0%";
}
```

---

## Зависимости

Ничего нового — всё уже есть в FastAPI. Только убедись что в `requirements.txt` есть:

```
fastapi
uvicorn
python-multipart   # нужен для UploadFile
```

`python-multipart` нужен FastAPI для обработки `multipart/form-data` (загрузка файлов). Без него `UploadFile` не работает.

---

## Важные решения и ограничения

### Хранилище состояний задач
В коде выше `jobs` — это обычный Python dict в памяти. Это работает для **одного воркера**. Если у тебя несколько воркеров uvicorn (`--workers N`), состояние будет разделено между процессами и polling сломается.

**Если используешь несколько воркеров:** замени `jobs` dict на Redis:
```python
import redis, json
r = redis.Redis()
# запись: r.setex(f"job:{job_id}", 700, json.dumps(state))
# чтение: json.loads(r.get(f"job:{job_id}"))
```

### Очистка файлов
Временные файлы удаляются через `asyncio.sleep(600)` после завершения задачи. Если сервер перезапустится в процессе — файлы останутся. Добавь startup-хук для очистки старых папок:
```python
@app.on_event("startup")
async def cleanup_old_jobs():
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True)
```

### Размер архива и таймауты
Conversations.json может весить 300+ MB. Обработка 950 диалогов занимает ~70 секунд. Убедись что у nginx/proxy нет таймаута на загрузку файла. Рекомендуемые настройки nginx:
```nginx
client_max_body_size 600M;
proxy_read_timeout   600s;
proxy_send_timeout   600s;
```

### Параллельные задачи
`run_in_executor` использует `ThreadPoolExecutor` по умолчанию (количество потоков = CPU * 5). При высокой нагрузке создай явный executor с ограничением:
```python
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=3)
await loop.run_in_executor(executor, _build_archive, ...)
```

---

## Порядок реализации для Claude Code

1. Скопировать `declaude.py` в корень проекта (или настроить `sys.path` в `claude_converter.py`)
2. Создать `routers/claude_archive.py` по шаблону выше
3. Создать `services/claude_converter.py`, импортировать `run_conversion` в роутер
4. Создать `templates/claude_archive.html` и `static/claude_archive.js`
5. Добавить `app.include_router(...)` в `main.py`
6. Добавить `python-multipart` в зависимости
7. Проверить что nginx разрешает загрузку файлов до 500 MB
