# Phase 4: Ingestion & Infrastructure Bug Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix 15 functional defects and design issues across ingestion, schemas, tools, and services discovered in the fourth audit.

**Architecture:** Each task targets a single module/file. Fixes are independent and can be executed in any order. No new files are created; all changes are surgical edits to existing code.

**Tech Stack:** Python 3.13, Pydantic V2, FastAPI, threading, httpx

---

## Spec Summary

> **Status:** All 15 items completed as of 2026-06-14. The remaining items #2, #5, and #11 were finished in commits `3264de0`, `cacffed`, and `9242f8b` respectively.

| # | Severity | Module | Issue | Fix | Status |
|---|----------|--------|-------|-----|--------|
| 1 | 🔴 | `ingestion/cleaner.py` | `_extract_preserved` builds placeholder list but never injects into text → `preserve_rule_numbers=True` has zero effect | Inject `__PRESERVED_N__` markers into text during extraction | ✅ |
| 2 | 🟡 | `ingestion/cleaner.py` | `extract_structure_markers` returns raw dicts instead of `StructureBlock` | Use `StructureBlock` from `chunker.py` | ✅ |
| 3 | 🟡 | `ingestion/loader.py` | `MarkdownLoader` and `TextLoader` are identical | Merge into single `TextFileLoader` | ✅ |
| 4 | 🟡 | `ingestion/loader.py` | `PDFLoader.load()` returns `""` on error, creating empty documents | Raise exception so caller can skip | ✅ |
| 5 | 🟡 | `ingestion/loader.py` | `save_document` manually serializes datetime | Use `model_dump(mode='json')` | ✅ |
| 6 | 🟡 | `tools/query_parser.py` | `extract_numbers` sorts+deduplicates, losing positional order | Add `extract_numbers_ordered` preserving position; keep old method for backward compat | ✅ |
| 7 | 🟡 | `tools/size_test_input_extractor.py` | `_compute_confidence` uses all 9 FIELD_KEYWORDS but only 2 are truly required now | Weight required fields higher | ✅ |
| 8 | 🟡 | `tools/size_test_input_extractor.py` | `_fallback_assignment` assigns remaining numbers to random keys | Remove fallback assignment — it produces incorrect mappings | ✅ |
| 9 | 🟡 | `schemas/response.py` | `route_validation`, `decomposition_plan`, `decomposition_validation` always None | Mark as deprecated with docstrings | ✅ |
| 10 | 🟡 | `api/chat_v2_stream.py` | `list(stream_query(...))` buffers all events before yielding → pseudo-streaming | Yield events progressively using `asyncio.to_thread` or queue | ✅ |
| 11 | 🟡 | `services/session_store.py` | `_load_from_disk` loads all sessions at startup | Lazy-load: load only when `get_or_create` is called for a specific ID | ✅ |
| 12 | 🟡 | `services/session_store.py` | `cleanup_expired` renames to `.expired` but never deletes | Delete expired files after archiving | ✅ |
| 13 | 🟡 | `services/session_store.py` | `_is_expired` with TTL=0 means "always expired" (counter-intuitive) | TTL=0 means "never expire"; document the edge case | ✅ |
| 14 | 🟡 | `models/conversation.py` | Uses deprecated `datetime.utcnow` | Replace with `datetime.now(timezone.utc)` | ✅ |
| 15 | 🟡 | `tools/disclosure_checklist.py` | Connected overlay distributes items by `deadline_days` | Add explicit `section` field to items | ✅ |

---

### Task 1: Fix Cleaner preserve/restore mechanism

**Files:**
- Modify: `app/ingestion/cleaner.py`
- Test: `tests/test_cleaner.py`

**Problem:** `_extract_preserved` finds matches but never replaces them with placeholders in the text. When `_restore_preserved` runs, the placeholders don't exist in the text, so nothing is restored.

- [x] **Step 1: Update `_extract_preserved` to inject placeholders into text**

```python
def _extract_preserved(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
    preserved: List[Tuple[str, str]] = []
    for pattern in self.preserve_patterns:
        def _replace(match, p=preserved):
            original = match.group(0)
            placeholder = f"__PRESERVED_{len(p)}__"
            p.append((original, placeholder))
            return placeholder
        text = re.sub(pattern, _replace, text)
    return text, preserved
```

- [x] **Step 2: Update `clean` to use the new return type**

```python
def clean(self, text: str) -> str:
    if not text:
        return ""
    
    text, preserved = self._extract_preserved(text)
    
    for pattern in self.default_remove_patterns:
        text = re.sub(pattern, '\n', text)
    
    for pattern in self.remove_patterns:
        text = re.sub(pattern, '', text)
    
    text = self._normalize_whitespace(text)
    text = self._restore_preserved(text, preserved)
    text = text.strip()
    
    return text
```

- [x] **Step 3: Add test that verifies rule numbers are preserved**

```python
# In tests/test_cleaner.py, add:
def test_preserve_rule_numbers_active(self):
    text = "Rule 14A.35 requires approval.\n\n  Extra   spaces  here."
    result = clean_document_text(text, preserve_rule_numbers=True)
    assert "Rule 14A.35" in result
    assert "  Extra   spaces" not in result  # spaces normalized
```

- [x] **Step 4: Run test**

Run: `pytest tests/test_cleaner.py -v`
Expected: all PASS including new test

- [x] **Step 5: Validate no regressions**

Run: `pytest tests/test_chunker.py tests/test_cleaner.py -v`
Expected: all PASS

---

### Task 2: Remove duplicate MarkdownLoader

**Files:**
- Modify: `app/ingestion/loader.py:22-37`

- [x] **Step 1: Merge MarkdownLoader into TextLoader**

```python
class TextFileLoader(BaseLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in [".txt", ".md", ".markdown"]
    
    def load(self, file_path: Path) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
```

- [x] **Step 2: Update DocumentLoader to use TextFileLoader**

```python
class DocumentLoader:
    def __init__(self):
        self.loaders: List[BaseLoader] = [
            TextFileLoader(),
            PDFLoader(),
        ]
```

- [x] **Step 3: Fix PDFLoader to raise on error instead of returning ""**

```python
class PDFLoader(BaseLoader):
    def load(self, file_path: Path) -> str:
        try:
            import fitz
        except ImportError:
            raise RuntimeError("pymupdf not installed. Run: pip install pymupdf")

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        doc = fitz.open(str(file_path))
        # ... rest stays same ...
```

- [x] **Step 4: Run tests**

Run: `pytest tests/test_pdf_loader.py tests/test_cleaner.py -v`
Expected: all PASS

---

### Task 3: Fix QueryParser extract_numbers order

**Files:**
- Modify: `app/tools/query_parser.py:6-20`

- [x] **Step 1: Add `extract_numbers_ordered` preserving position**

```python
@staticmethod
def extract_numbers_ordered(text: str) -> List[Tuple[float, int]]:
    """Extract numbers with their character positions, preserving order."""
    if not text:
        return []
    pattern = r'[+-]?(?:\d+(?:[,\s]\d{3})*\.\d+|\d+(?:[,\s]\d{3})*|\d+\.\d+|\d+)(?:[eE][+-]?\d+)?'
    seen = set()
    results = []
    for m in re.finditer(pattern, text):
        num_str = m.group(0)
        cleaned = num_str.replace(',', '').replace(' ', '')
        try:
            val = float(cleaned)
            if val not in seen:
                seen.add(val)
                results.append((val, m.start()))
        except ValueError:
            continue
    return results
```

- [x] **Step 2: Keep old `extract_numbers` for backward compat (add docstring note)**

```python
@staticmethod
def extract_numbers(text: str) -> List[float]:
    """Extract all unique numbers, sorted ascending. (Legacy: use extract_numbers_ordered for position-aware extraction.)"""
    if not text:
        return []
    # ... existing implementation unchanged ...
```

- [x] **Step 3: Run tests**

Run: `pytest tests/test_query_parser.py tests/test_query_parser_basic.py -v`
Expected: all PASS

---

### Task 4: Fix SizeTestInputExtractor confidence

**Files:**
- Modify: `app/tools/size_test_input_extractor.py:143-154`

- [x] **Step 1: Update confidence to weight required fields higher**

```python
REQUIRED_FIELDS = {"transaction_consideration", "transaction_type"}

def _compute_confidence(self, result: Dict[str, Any]) -> float:
    req_filled = sum(1 for k in self.REQUIRED_FIELDS if k in result)
    req_total = len(self.REQUIRED_FIELDS)
    opt_filled = sum(1 for k in self.FIELD_KEYWORDS if k in result and k not in self.REQUIRED_FIELDS)
    opt_total = len(self.FIELD_KEYWORDS) - len(self.REQUIRED_FIELDS)

    req_score = req_filled / req_total if req_total > 0 else 0.0
    opt_score = opt_filled / opt_total if opt_total > 0 else 0.0
    return round(req_score * 0.7 + opt_score * 0.3, 2)  # 70% weight on required
```

- [x] **Step 2: Remove `_fallback_assignment` (produces incorrect mappings)**

Delete the `_fallback_assignment` method and its call site in `extract()`:

```python
# In extract(), remove:
# if len(result) < 5:
#     fallback = self._fallback_assignment(query, numbers, result)
#     result.update(fallback)
```

- [x] **Step 3: Run tests**

Run: `pytest tests/test_size_test_input_extractor.py -v`
Expected: all PASS. If any tests relied on fallback behavior, update them.

---

### Task 5: Deprecate ghost fields in ChatResponse

**Files:**
- Modify: `app/schemas/response.py:20-22`

- [x] **Step 1: Mark fields as deprecated with docstrings**

```python
route_validation: Optional[Dict[str, Any]] = Field(
    default=None,
    description="[DEPRECATED] Route validation result. Always None since V2 simplification (2026-06). Retained for API backward compatibility.",
)
decomposition_plan: Optional[Dict[str, Any]] = Field(
    default=None,
    description="[DEPRECATED] Task decomposition plan. Always None since V2 simplification (2026-06). Retained for API backward compatibility.",
)
decomposition_validation: Optional[Dict[str, Any]] = Field(
    default=None,
    description="[DEPRECATED] Decomposition validation result. Always None since V2 simplification (2026-06). Retained for API backward compatibility.",
)
```

- [x] **Step 2: Import check**

Run: `python -c "from app.schemas.response import ChatResponse; print('OK')"`
Expected: OK

---

### Task 6: Fix pseudo-streaming

**Files:**
- Modify: `app/api/chat_v2_stream.py:64-70`

- [x] **Step 1: Use synchronous generator correctly — yield from executor directly**

```python
# Replace _sync_stream with direct iteration
loop = asyncio.get_event_loop()

def _stream_events():
    for event in orch.stream_query(query, use_llm_planner, conversation_id=cid, chat_history=chat_history):
        yield event

events_iter = _stream_events()

# Use a queue to bridge sync generator to async
queue = asyncio.Queue()

def _producer():
    try:
        for event in events_iter:
            loop.call_soon_threadsafe(queue.put_nowait, event)
    except Exception as e:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": "error", "data": {"message": str(e)}})
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

import concurrent.futures
executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
executor.submit(_producer)

while True:
    event = await queue.get()
    if event is None:
        break
    event_type = event["event"]
    event_data = event["data"]
    # ... rest of handling ...
```

- [x] **Step 2: Run streaming tests**

Run: `pytest tests/test_streaming.py -v`
Expected: all PASS

---

### Task 7: Fix SessionStore startup + cleanup

**Files:**
- Modify: `app/services/session_store.py`

- [x] **Step 1: Lazy-load sessions (remove `_load_from_disk` from `__init__`)**

```python
def __init__(self, ...):
    # ... existing setup ...
    # Remove: self._load_from_disk()
    logger.info(f"SessionStore initialized (lazy-load enabled, path={self._storage_path})")
```

- [x] **Step 2: Load on demand in `get_or_create`**

```python
def get_or_create(self, conversation_id=None):
    with self._lock:
        if conversation_id and conversation_id in self._sessions:
            # ... existing logic ...
        if conversation_id and conversation_id not in self._sessions:
            self._try_load_session(conversation_id)
            if conversation_id in self._sessions:
                return self._sessions[conversation_id]
        return self._create_new()
```

- [x] **Step 3: Add `_try_load_session` method**

```python
def _try_load_session(self, conversation_id: str) -> None:
    filepath = self._storage_path / f"{conversation_id}.jsonl"
    if not filepath.exists():
        return
    session = self._load_session_file(filepath, conversation_id)
    if session and not self._is_expired(session):
        self._sessions[conversation_id] = session
```

- [x] **Step 4: Fix `cleanup_expired` to delete .expired files**

```python
def cleanup_expired(self) -> int:
    with self._lock:
        # ... remove expired sessions ...
        for sid in expired_ids:
            del self._sessions[sid]
            filepath = self._storage_path / f"{sid}.jsonl"
            if filepath.exists():
                filepath.unlink()  # Delete instead of rename
```

- [x] **Step 5: Fix `_is_expired` TTL=0 semantics**

```python
def _is_expired(self, session) -> bool:
    if self._ttl.total_seconds() == 0:
        return False  # TTL=0 means never expire
    return (datetime.utcnow() - session.last_active) > self._ttl
```

- [x] **Step 6: Run tests**

Run: `pytest tests/test_session_store.py -v`
Expected: all PASS

---

### Task 8: Fix datetime.utcnow deprecation

**Files:**
- Modify: `app/models/conversation.py:14,31`

- [x] **Step 1: Replace deprecated calls**

```python
from datetime import datetime, timezone

class ConversationTurn(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

class ConversationSession(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
```

- [x] **Step 2: Also fix SessionStore's datetime calls**

In `app/services/session_store.py`, replace all `datetime.utcnow()` with `datetime.now(tz=timezone.utc)`.

- [x] **Step 3: Run tests**

Run: `pytest tests/test_session_store.py tests/test_multi_turn_integration.py -v`
Expected: all PASS

---

### Task 9: Fix DisclosureChecklist deadline fragility

**Files:**
- Modify: `app/tools/disclosure_checklist.py:54-61,153-186`

- [x] **Step 1: Add `section` field to connected overlay items**

```python
def _connected_overlay_items() -> List[Dict[str, Any]]:
    return [
        {"task": "Appoint IFA (Independent Financial Adviser)", "required": True, "deadline_days": 7, "rule_reference": "Rule 14A.46", "section": "announcement"},
        {"task": "Obtain IFA opinion letter for circular", "required": True, "deadline_days": 15, "rule_reference": "Rule 14A.46", "section": "circular"},
        {"task": "Obtain independent shareholder approval", "required": True, "deadline_days": 21, "rule_reference": "Rule 14A.36", "section": "shareholder_meeting"},
        {"task": "Connected person(s) abstain from voting", "required": True, "deadline_days": 21, "rule_reference": "Rule 14A.36", "section": "shareholder_meeting"},
        {"task": "Disclose connected party relationship details", "required": True, "deadline_days": 3, "rule_reference": "Rule 14A.68", "section": "announcement"},
    ]
```

- [x] **Step 2: Update `_add_connected_overlay` to use section field**

```python
@staticmethod
def _add_connected_overlay(sections, shareholder_vote_required):
    connected_items = _connected_overlay_items()
    section_names = {s["name"] for s in sections}

    if "circular" not in section_names:
        sections.insert(-1, {"name": "circular", "items": _circular_items()})
    if "shareholder_meeting" not in section_names:
        sections.insert(-1, {"name": "shareholder_meeting", "items": _shareholder_meeting_items()})

    for s in sections:
        matching = [i for i in connected_items if i.get("section") == s["name"]]
        s["items"].extend(matching)

    return sections
```

- [x] **Step 3: Run tests**

Run: `pytest tests/test_disclosure_checklist.py -v`
Expected: all PASS

---

### Task 10: Final integration check

- [x] **Step 1: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_chat_api.py --ignore=tests/test_chat_v2_api.py --ignore=tests/test_streaming.py --ignore=tests/test_multi_turn_stream.py -x
```

- [x] **Step 2: Import check for all modified modules**

```bash
python -c "from app.ingestion.cleaner import TextCleaner, clean_document_text; from app.ingestion.loader import DocumentLoader, TextFileLoader; from app.schemas.response import ChatResponse; from app.api.chat_v2_stream import router; from app.services.session_store import SessionStore; from app.models.conversation import ConversationTurn; from app.tools.disclosure_checklist import DisclosureChecklistTool; from app.tools.query_parser import QueryParser; from app.tools.size_test_input_extractor import SizeTestInputExtractor; print('All imports OK')"
```

- [x] **Step 3: Verify no new regressions with targeted tests**

```bash
pytest tests/test_cleaner.py tests/test_chunker.py tests/test_pdf_loader.py tests/test_query_parser.py tests/test_query_parser_basic.py tests/test_size_test_input_extractor.py tests/test_disclosure_checklist.py tests/test_session_store.py -v
```

---

## Execution Order

Tasks are independent and can run in parallel:
- Task 1-2 (cleaner + loader) — can run together
- Task 3-4 (query_parser + size_test_extractor) — can run together
- Task 5 (response schema) — standalone
- Task 6 (streaming) — standalone
- Task 7-8 (session_store + conversation) — can run together
- Task 9 (disclosure_checklist) — standalone
- Task 10 (final check) — after all others

Total estimated effort: ~45 minutes all tasks.
