"""Gravações locais substituídas por inteiro e leitura conservadora do histórico."""

import json
import math
import os
from pathlib import Path
import tempfile


def atomic_json(path: Path, data: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=path.parent,
                                         prefix=f".{path.name}-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def paragraph_log(path: Path) -> tuple[list[dict], list[str]]:
    """Aceitar só uma cauda sem JSON completo e sem quebra de linha final.

    Validar o arquivo antes de importar impede que corrupção intermediária seja
    disfarçada como uma recuperação parcial. O arquivo original não é alterado.
    """
    if not path.is_file():
        return [], []
    raw = path.read_bytes()
    lines = raw.split(b"\n")
    records, warnings = [], []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line.decode("utf8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if index == len(lines) and not raw.endswith(b"\n"):
                warnings.append(f"paragraphs.jsonl: última linha ({index}) incompleta ou inválida; "
                                "não importada. O arquivo original foi preservado.")
                break
            raise ValueError(f"paragraphs.jsonl: linha {index} inválida. A importação foi bloqueada; "
                             "preserve a pasta para investigação.") from None
        if (not isinstance(data, dict) or type(data.get("paragraph_id")) is not int or data["paragraph_id"] <= 0
                or type(data.get("version")) is not int or data["version"] <= 0
                or not isinstance(data.get("source_text"), str)
                or not isinstance(data.get("text"), str)
                or ("closed" in data and not isinstance(data["closed"], bool))
                or (data.get("speaker") is not None and not isinstance(data["speaker"], str))
                or ("parts" in data and not isinstance(data["parts"], list))
                or any(type(data.get(key)) not in {int, float} or not math.isfinite(data[key]) for key in ("start", "end"))
                or data["start"] < 0 or data["end"] < data["start"]):
            raise ValueError(f"paragraphs.jsonl: registro incompatível na linha {index}. A importação foi bloqueada.")
        records.append(data)
    return records, warnings
