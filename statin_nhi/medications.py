"""New-system medication catalog and portable hospital medication settings."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys


CATALOG_FILENAME = "Statin 健保新制可用藥物清單.csv"
SETTINGS_FILENAME = "Statin_NHI_available.json"
REQUIRED_COLUMNS = ("code", "display_name", "ingredient", "category", "effective_date")
CATEGORY_ORDER = (
    "高強度 Statin",
    "中強度 Statin",
    "低強度 Statin",
    "輔助藥物",
    "複方藥物",
)


@dataclass(frozen=True)
class Medication:
    code: str
    display_name: str
    ingredient: str
    category: str
    effective_date: date

    def is_effective(self, as_of: date | None = None) -> bool:
        return self.effective_date <= (as_of if as_of is not None else taiwan_today())

    @property
    def display_label(self) -> str:
        return f"{self.display_name} ({self.ingredient})"


class MedicationCatalog:
    def __init__(self, medications: list[Medication]) -> None:
        self._by_code = {medication.code: medication for medication in medications}

    @classmethod
    def from_csv(cls, path: Path) -> "MedicationCatalog":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or tuple(reader.fieldnames) != REQUIRED_COLUMNS:
                raise ValueError(f"藥物主檔欄位必須為：{', '.join(REQUIRED_COLUMNS)}")
            medications = []
            for row_number, row in enumerate(reader, start=2):
                values = {column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS}
                if not all(values.values()):
                    raise ValueError(f"藥物主檔第 {row_number} 列缺少必要資料。")
                code = normalize_medication_code(values["code"])
                if not code:
                    raise ValueError(f"藥物主檔第 {row_number} 列的健保代碼格式無效。")
                try:
                    effective_date = date.fromisoformat(values["effective_date"])
                    if effective_date.isoformat() != values["effective_date"]:
                        raise ValueError
                except ValueError as error:
                    raise ValueError(f"藥物主檔第 {row_number} 列的生效日必須為有效 YYYY-MM-DD。") from error
                medications.append(Medication(
                    code=code, effective_date=effective_date,
                    **{key: values[key] for key in REQUIRED_COLUMNS if key not in ("code", "effective_date")},
                ))

        if len({medication.code for medication in medications}) != len(medications):
            raise ValueError("藥物主檔含有重複健保代碼。")
        return cls(medications)

    def lookup(self, code: str) -> Medication | None:
        return self._by_code.get(normalize_medication_code(code))

    def selected(self, codes: list[str]) -> list[Medication]:
        selected: list[Medication] = []
        seen: set[str] = set()
        for code in codes:
            medication = self.lookup(code)
            if medication is not None and medication.code not in seen:
                selected.append(medication)
                seen.add(medication.code)
        return selected


def application_directory() -> Path:
    """Keep portable hospital settings beside the executable or source entry point."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", application_directory()))
    return base_path / relative_path


def default_catalog_path() -> Path:
    return bundled_resource_path(str(Path("Ref") / CATALOG_FILENAME))


def default_settings_path() -> Path:
    return application_directory() / SETTINGS_FILENAME


def normalize_medication_code(value: str) -> str:
    code = re.sub(r"\s+", "", value).upper()
    return code if re.fullmatch(r"[A-Z]{2}\d{8}", code) else ""


def load_hospital_medication_codes(path: Path, catalog: MedicationCatalog) -> tuple[list[str], str | None]:
    if not path.exists():
        return [], None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], "院內藥物設定檔無法讀取，未載入任何藥物。"
    if not isinstance(payload, dict) or not isinstance(payload.get("medication_codes"), list):
        return [], "院內藥物設定檔格式無效，未載入任何藥物。"
    return [medication.code for medication in catalog.selected([str(code) for code in payload["medication_codes"]])], None


def save_hospital_medication_codes(path: Path, codes: list[str], catalog: MedicationCatalog) -> list[str]:
    selected_codes = [medication.code for medication in catalog.selected(codes)]
    payload = _settings_with_legacy_reminders(path)
    payload["medication_codes"] = selected_codes
    _write_settings(path, payload)
    return selected_codes


def taiwan_today() -> date:
    """Use Taiwan's date even when the execution host runs in UTC."""
    return datetime.now(timezone(timedelta(hours=8))).date()


def medication_output_lines(medications: list[Medication], as_of: date | None = None) -> list[str]:
    as_of = as_of if as_of is not None else taiwan_today()
    grouped: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
    for medication in medications:
        if not medication.is_effective(as_of):
            continue
        grouped.setdefault(medication.category, []).append(medication.display_label)

    lines = []
    for category in CATEGORY_ORDER:
        if grouped[category]:
            lines.append(f"新制可用{category}：{', '.join(grouped[category])}")
    for category, labels in grouped.items():
        if category not in CATEGORY_ORDER and labels:
            lines.append(f"新制可用{category}：{', '.join(labels)}")
    return lines


REIMBURSEMENT_UPDATE_ID = "1150672925"
NEW_MEDICATION_CODES = (
    "AC57930100", "BC25350100", "BC27002100",
    "AC62140100", "AC62139100", "BC28884100",
)
REMINDER_FILENAME = "Statin_NHI_reminders.json"


def _read_settings(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"medication_codes": []}
    except (ValueError, UnicodeError) as error:
        raise OSError("院內設定檔格式錯誤，為保留原始資料，未覆寫設定。") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("medication_codes"), list):
        raise OSError("院內設定檔格式錯誤，為保留原始資料，未覆寫設定。")
    if "dismissed_updates" in payload and not isinstance(payload["dismissed_updates"], dict):
        raise OSError("公告提醒設定格式錯誤，未覆寫設定。")
    return payload


def _settings_with_legacy_reminders(path: Path) -> dict:
    payload = _read_settings(path)
    try:
        legacy = json.loads(path.with_name(REMINDER_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        legacy = {}
    if isinstance(legacy, dict):
        updates = {key: value for key, value in legacy.items() if value is True}
        updates.update(payload.get("dismissed_updates", {}))
        if updates:
            payload["dismissed_updates"] = updates
    return payload


def _write_settings(path: Path, payload: dict) -> None:
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def should_show_medication_update(codes: list[str], settings_path: Path) -> bool:
    """Any configured new code means the hospital has reviewed this update."""
    try:
        original = _read_settings(settings_path)
        payload = _settings_with_legacy_reminders(settings_path)
        if payload != original:
            try:
                _write_settings(settings_path, payload)
            except OSError:
                pass  # Keep honoring the legacy file if migration cannot be saved.
    except OSError:
        payload = {}
    if set(map(normalize_medication_code, codes)).intersection(NEW_MEDICATION_CODES):
        return False
    return payload.get("dismissed_updates", {}).get(REIMBURSEMENT_UPDATE_ID) is not True


def dismiss_medication_update(path: Path) -> None:
    payload = _settings_with_legacy_reminders(path)
    payload.setdefault("dismissed_updates", {})[REIMBURSEMENT_UPDATE_ID] = True
    _write_settings(path, payload)
