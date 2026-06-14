# Phase 4 剩余缺陷修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 完成 Phase 4  ingestion & infrastructure 修复计划中尚未解决的 3 个模块：`cleaner.py` 结构标记模型化、`loader.py` JSON 序列化标准化、`session_store.py` 会话懒加载。

**Architecture：** 三个修复彼此独立，可分别实现、分别测试。`StructureBlock` 复用 `chunker.py` 中已定义的 dataclass；`save_document` 改用 Pydantic 原生 JSON 序列化；`SessionStore` 移除启动时全量加载，改为按 `conversation_id` 首次访问时加载。

**Tech Stack：** Python 3.13, Pydantic V2, dataclasses, threading

---

## Spec Summary

| # | 模块 | 文件路径 | 当前问题 | 目标修复 |
|---|---|---|---|---|
| 1 | TextCleaner 结构标记提取 | `app/ingestion/cleaner.py` | `extract_structure_markers()` 返回 `List[dict]` | 返回 `List[StructureBlock]`（复用 `chunker.py` 的 dataclass） |
| 2 | Document 保存序列化 | `app/ingestion/loader.py` | `save_document()` 手动调用 `.isoformat()` 序列化 datetime | 使用 `document.model_dump(mode='json')` |
| 3 | SessionStore 启动加载 | `app/services/session_store.py` | `__init__()` 调用 `_load_from_disk()` 全量加载所有历史会话 | 按需懒加载：仅在访问某个 `conversation_id` 时加载对应会话 |

---

## Task 1: TextCleaner 返回 StructureBlock 而非 dict

**Files:**
- Modify: `app/ingestion/cleaner.py:1-3`（imports）, `app/ingestion/cleaner.py:77-106`（`extract_structure_markers`）
- Test: `tests/test_cleaner.py`

**Problem:** `TextCleaner.extract_structure_markers()` 手动构造 `dict`，导致下游缺少类型提示、字段无校验，与项目整体 Pydantic/dataclass 风格不一致。

**Design:** 复用 `app/ingestion/chunker.py` 中已定义的 `StructureBlock` dataclass。将 cleaner 中的单点 marker 映射为：
- `block_type` ← `type` 字段值（`'chapter'`, `'section'`, `'rule'`）
- `number` ← 匹配到的编号
- `title` ← `None`（cleaner 只提取 marker，不解析标题）
- `start_pos` ← `match.start()`
- `end_pos` ← `match.end()`
- `text` ← `match.group(0)`
- `parent_chapter`, `parent_section` ← `None`

- [x] **Step 1: 导入 StructureBlock**

```python
from typing import List, Tuple, Optional
from app.core.logger import logger
from app.ingestion.chunker import StructureBlock
```

- [x] **Step 2: 修改 extract_structure_markers 返回类型和实现**

```python
def extract_structure_markers(self, text: str) -> List[StructureBlock]:
    markers: List[StructureBlock] = []

    for match in self.chapter_pattern.finditer(text):
        markers.append(StructureBlock(
            block_type='chapter',
            number=match.group(1),
            title=None,
            start_pos=match.start(),
            end_pos=match.end(),
            text=match.group(0),
            parent_chapter=None,
            parent_section=None,
        ))

    for match in self.section_pattern.finditer(text):
        markers.append(StructureBlock(
            block_type='section',
            number=match.group(1),
            title=None,
            start_pos=match.start(),
            end_pos=match.end(),
            text=match.group(0),
            parent_chapter=None,
            parent_section=None,
        ))

    for match in self.rule_number_pattern.finditer(text):
        markers.append(StructureBlock(
            block_type='rule',
            number=match.group(1),
            title=None,
            start_pos=match.start(),
            end_pos=match.end(),
            text=match.group(0),
            parent_chapter=None,
            parent_section=None,
        ))

    markers.sort(key=lambda x: x.start_pos)
    return markers
```

- [x] **Step 3: 在 tests/test_cleaner.py 添加/更新测试**

```python
def test_extract_structure_markers_returns_structure_blocks():
    text = "Chapter 14A states Rule 14A.35. Section 14A.1 explains."
    cleaner = TextCleaner()
    markers = cleaner.extract_structure_markers(text)

    assert all(isinstance(m, StructureBlock) for m in markers)
    assert len(markers) == 3

    types = [m.block_type for m in markers]
    assert types == ['chapter', 'rule', 'section']

    chapter = markers[0]
    assert chapter.number == '14A'
    assert chapter.text == 'Chapter 14A'
    assert chapter.start_pos < chapter.end_pos
    assert chapter.title is None
```

- [x] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_cleaner.py -v`

Expected: all PASS

- [x] **Step 5: 检查是否有其他调用方依赖 dict 字段名**

Run: `grep -rn "extract_structure_markers" app/ tests/`

Expected: 仅 `cleaner.py` 自身和 `tests/test_cleaner.py` 使用；如有外部调用，更新字段访问方式（`marker['type']` → `marker.block_type`，`marker['position']` → `marker.start_pos`）。

- [x] **Step 6: 运行相关回归测试**

Run: `pytest tests/test_cleaner.py tests/test_chunker.py -v`

Expected: all PASS

- [x] **Step 7: Commit**

```bash
git add app/ingestion/cleaner.py tests/test_cleaner.py
git commit -m "refactor(cleaner): return StructureBlock from extract_structure_markers"
```

---

## Task 2: save_document 使用 model_dump(mode='json')

**Files:**
- Modify: `app/ingestion/loader.py:146-160`
- Test: `tests/test_loader.py`（如存在）或 `tests/test_document.py`

**Problem:** `save_document()` 先调用 `document.model_dump()` 得到 Python 对象，再手动判断 `metadata.imported_at` 并调用 `.isoformat()`。这种方式脆弱，新增 datetime 字段时容易遗漏。

**Design:** 使用 Pydantic V2 的 `model_dump(mode='json')`，它会自动将 `datetime` 序列化为 ISO 8601 字符串，无需手动处理。

- [x] **Step 1: 修改 save_document 实现**

```python
def save_document(document: Document, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{document.document_id}.json"

    doc_dict = document.model_dump(mode='json')

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc_dict, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved document to: {output_path}")
    return output_path
```

- [x] **Step 2: 在 tests/ 添加 round-trip 测试**

若 `tests/test_loader.py` 不存在，在 `tests/test_cleaner.py` 或新建 `tests/test_loader.py` 添加：

```python
from datetime import datetime, timezone
from pathlib import Path
from app.ingestion.loader import save_document, load_document_from_json
from app.schemas.document import Document, DocumentMetadata


def test_save_document_round_trip(tmp_path):
    doc = Document(
        document_id="test-doc-1",
        source_path="/tmp/test.md",
        source_type="md",
        title="Test Document",
        raw_text="Hello",
        cleaned_text="Hello",
        metadata=DocumentMetadata(
            imported_at=datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc),
            source_url="https://example.com",
            page_count=5,
        ),
    )

    output_path = save_document(doc, tmp_path)
    assert output_path.exists()

    restored = load_document_from_json(output_path)
    assert restored.document_id == doc.document_id
    assert restored.metadata.imported_at == doc.metadata.imported_at
    assert restored.metadata.source_url == doc.metadata.source_url
    assert restored.metadata.page_count == doc.metadata.page_count
```

- [x] **Step 3: 运行测试确认通过**

Run: `pytest tests/test_loader.py -v`（或包含新测试的文件）

Expected: all PASS

- [x] **Step 4: 验证 JSON 输出不含 Python datetime 对象**

Run 临时脚本：

```python
from datetime import datetime, timezone
from pathlib import Path
from app.schemas.document import Document, DocumentMetadata
from app.ingestion.loader import save_document
import json

doc = Document(
    document_id="dt-check",
    source_path="x",
    source_type="md",
    title="x",
    metadata=DocumentMetadata(imported_at=datetime.now(timezone.utc)),
)
path = save_document(doc, Path("/tmp/dt_test"))
with open(path) as f:
    data = json.load(f)
assert isinstance(data["metadata"]["imported_at"], str)
print("OK:", data["metadata"]["imported_at"])
```

Expected: 打印 `OK: 2026-...` 且无异常

- [x] **Step 5: 运行相关回归测试**

Run: `pytest tests/test_cleaner.py tests/test_chunker.py tests/test_loader.py -v`

Expected: all PASS

- [x] **Step 6: Commit**

```bash
git add app/ingestion/loader.py tests/test_loader.py
git commit -m "refactor(loader): use model_dump(mode='json') in save_document"
```

---

## Task 3: SessionStore 按需懒加载会话

**Files:**
- Modify: `app/services/session_store.py:25-80`
- Test: `tests/test_session_store.py`

**Problem:** `SessionStore.__init__()` 第 37 行直接调用 `self._load_from_disk()`，导致每次实例化都扫描并加载 `data/sessions/` 下所有历史 JSONL 文件，造成启动延迟、不必要的 I/O 和内存占用。

**Design：**
- 移除 `__init__` 中的 `_load_from_disk()` 调用。
- 在 `get_or_create(conversation_id)` 中，如果内存缓存未命中且 `conversation_id` 非空，尝试从磁盘加载该 ID 对应的 JSONL 文件；若文件存在且未过期则缓存，否则创建新会话。
- 保持 `_load_from_disk()` 方法作为内部工具方法（可用于一次性迁移/调试），但不再由 `__init__` 自动调用。

- [x] **Step 1: 修改 SessionStore.__init__ 移除启动加载**

```python
def __init__(
    self,
    storage_path: Optional[Path] = None,
    ttl_minutes: int = 60,
    max_turns: int = 50,
):
    self._storage_path = Path(storage_path) if storage_path else Path("data/sessions")
    self._storage_path.mkdir(parents=True, exist_ok=True)
    self._ttl = timedelta(minutes=ttl_minutes)
    self._max_turns = max_turns
    self._sessions: Dict[str, ConversationSession] = {}
    self._lock = threading.Lock()
    # NOTE: sessions are loaded lazily on first access
```

- [x] **Step 2: 新增 _load_session 方法，加载单个会话**

在 `SessionStore` 中添加：

```python
def _load_session(self, conversation_id: str) -> Optional[ConversationSession]:
    """Load a single session from disk if its JSONL file exists."""
    file_path = self._storage_path / f"{conversation_id}.jsonl"
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            turns = [ConversationTurn.model_validate_json(line) for line in f if line.strip()]
    except Exception as e:
        logger.warning(f"Failed to load session {conversation_id}: {e}")
        return None

    if not turns:
        return None

    session = ConversationSession(conversation_id=conversation_id, turns=turns)
    if self._is_expired(session):
        logger.info(f"Loaded session {conversation_id} is expired")
        return None

    session.last_active = datetime.now(tz=timezone.utc)
    return session
```

- [x] **Step 3: 修改 get_or_create 增加懒加载路径**

```python
def get_or_create(self, conversation_id: Optional[str] = None) -> ConversationSession:
    with self._lock:
        if conversation_id and conversation_id in self._sessions:
            session = self._sessions[conversation_id]
            if self._is_expired(session):
                logger.info(f"Session {conversation_id} expired, creating new")
                del self._sessions[conversation_id]
                return self._create_new()
            session.last_active = datetime.now(tz=timezone.utc)
            return session

        if conversation_id:
            session = self._load_session(conversation_id)
            if session is not None:
                self._sessions[conversation_id] = session
                return session
            logger.debug(f"Session {conversation_id} not found, creating new")

        return self._create_new()
```

- [x] **Step 4: 更新 docstring 说明懒加载行为**

```python
class SessionStore:
    """Thread-safe in-memory session store with JSONL file persistence.

    Sessions are loaded lazily: a session file is read from disk only when
    `get_or_create(conversation_id)` is called for a specific ID that is not
    already cached in memory. This avoids scanning all historical sessions at
    startup.
    """
```

- [x] **Step 5: 在 tests/test_session_store.py 添加懒加载测试**

```python
def test_lazy_load_only_loads_requested_session(self, tmp_path):
    # Pre-create two session files on disk
    session_a_id = "session-a"
    session_b_id = "session-b"

    file_a = tmp_path / f"{session_a_id}.jsonl"
    file_b = tmp_path / f"{session_b_id}.jsonl"

    turn_a = ConversationTurn(role="user", content="hello A")
    turn_b = ConversationTurn(role="user", content="hello B")

    file_a.write_text(turn_a.model_dump_json() + "\n", encoding="utf-8")
    file_b.write_text(turn_b.model_dump_json() + "\n", encoding="utf-8")

    store = SessionStore(storage_path=tmp_path)
    assert len(store._sessions) == 0  # no eager loading

    session = store.get_or_create(session_a_id)
    assert session.conversation_id == session_a_id
    assert len(session.turns) == 1
    assert session.turns[0].content == "hello A"
    assert len(store._sessions) == 1

    # session-b should still not be loaded
    assert session_b_id not in store._sessions
```

- [x] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_session_store.py -v`

Expected: all PASS

- [x] **Step 7: 运行相关回归测试**

Run: `pytest tests/test_session_store.py tests/test_chat.py tests/test_api.py -v`

Expected: all PASS

- [x] **Step 8: Commit**

```bash
git add app/services/session_store.py tests/test_session_store.py
git commit -m "refactor(session_store): lazy-load sessions on first access"
```

---

## Final Verification

- [x] **Step 1: 运行全量测试套件**

Run: `pytest -q`

Expected: 390+ passed, no failures

- [x] **Step 2: 运行 Phase 4 相关定向测试**

Run:

```bash
pytest tests/test_cleaner.py tests/test_pdf_loader.py tests/test_query_parser.py \
       tests/test_size_test_input_extractor.py tests/test_session_store.py \
       tests/test_disclosure_checklist.py tests/test_streaming.py -q
```

Expected: all PASS

- [x] **Step 3: 更新 AGENTS.md（如需要）**

检查 `AGENTS.md` 中是否有关于 `SessionStore` 启动加载或 `save_document` 序列化的旧描述，如有则同步更新。

---

## Risk & Rollback

| 风险点 | 影响 | 缓解措施 |
|---|---|---|
| `StructureBlock` 字段名与原有 dict 不同 | 若外部代码仍用 `marker['type']` 访问会报错 | Step 5 已要求全局 grep；测试覆盖常见调用路径 |
| `model_dump(mode='json')` 与旧手动序列化格式细微差异 | datetime 格式仍为 ISO 8601，通常无影响；但 `ensure_ascii=False` 和 indent 已保留 | round-trip 测试验证 |
| 懒加载后 `SessionStore` 初始化时 `_sessions` 为空 | 任何依赖启动即全量缓存的代码会受影响 | 检查 `_load_from_disk` 的其它调用方；API 层均通过 `get_or_create` 访问，已覆盖 |
| 并发下首次访问同一 session 可能重复加载 | 已在 `get_or_create` 中使用 `self._lock` | 现有锁机制已保证线程安全 |

**Rollback：** 每个 Task 均为独立 commit，如出现问题可分别 revert。
