import json
import shutil
from pathlib import Path
from typing import Any, Iterable, List, Optional, Type

from pydantic import BaseModel


def read_jsonl(path: Path, model: Optional[Type[BaseModel]] = None) -> List[Any]:
    path = Path(path)
    records: List[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                records.append(model.model_validate(payload) if model else payload)
            except Exception as exc:
                raise ValueError(f"Invalid JSONL record at {path}:{line_number}: {exc}") from exc
    return records


def write_jsonl(path: Path, records: Iterable[Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            if isinstance(record, BaseModel):
                payload = record.model_dump(mode="json")
            else:
                payload = record
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    _replace_temporary_file(temporary, path)


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    _replace_temporary_file(temporary, path)


def _replace_temporary_file(temporary: Path, path: Path) -> None:
    try:
        temporary.replace(path)
    except PermissionError:
        # Windows can reject os.replace while the prior result is briefly observed.
        # Copying over the already-complete file preserves checkpointed evaluation rows.
        shutil.copyfile(temporary, path)
        temporary.unlink(missing_ok=True)
