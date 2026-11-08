from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Optional


def parse_clinical_date(value: str) -> date | None:
    """Parse ROC or Gregorian clinical dates into a Gregorian ``date``."""
    compact = re.fullmatch(r"\s*(\d{7}|\d{8})\s*", value)
    if compact:
        digits = compact.group(1)
        if len(digits) == 7:
            year, month, day = int(digits[:3]), int(digits[3:5]), int(digits[5:])
        else:
            year, month, day = int(digits[:4]), int(digits[4:6]), int(digits[6:])
    else:
        match = re.fullmatch(r"\s*(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})\s*", value)
        if not match:
            return None
        year, month, day = (int(part) for part in match.groups())
    if year < 1000:
        year += 1911
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_roc_date(value: date) -> str:
    """Return the date format used by the clinical input form."""
    return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"


@dataclass
class PatientData:
    note_text: str = ""
    sex: str = ""
    age: Optional[float] = None

    smoking: bool = False
    family_history_early_cad: bool = False
    metabolic_syndrome: bool = False

    recent_mi_within_1y: bool = False
    recurrent_mi: bool = False
    multivessel_coronary_disease: bool = False

    diabetes: bool = False
    hypertension: bool = False
    ascvd_history: bool = False
    acute_coronary_syndrome: bool = False
    coronary_revascularization: bool = False
    ischemic_stroke_tia: bool = False
    peripheral_arterial_disease: bool = False
    ckd_persistent_3m: bool = False
    on_dialysis: bool = False

    carotid_stenosis: bool = False
    arterial_stenosis_ge_50: bool = False
    coronary_stenosis_ge_50: bool = False
    peripheral_stenosis_ge_50: bool = False
    carotid_stenosis_ge_50: bool = False

    on_tg_medication: bool = False
    on_lipid_lowering_medication: bool = False
    on_statin_medication: bool = False

    total_cholesterol: Optional[float] = None
    ldl_c: Optional[float] = None
    hdl_c: Optional[float] = None
    triglycerides: Optional[float] = None
    fasting_glucose: Optional[float] = None
    waist_cm: Optional[float] = None
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    cac_score: Optional[float] = None

    creatinine_latest: Optional[float] = None
    creatinine_past: Optional[float] = None
    creatinine_month_gap: Optional[float] = None
    creatinine_latest_date: str = ""
    creatinine_past_date: str = ""

    egfr_date_1: str = ""
    egfr_value_1: Optional[float] = None
    egfr_date_2: str = ""
    egfr_value_2: Optional[float] = None

    uacr_date_1: str = ""
    uacr_value_1: Optional[float] = None
    uacr_date_2: str = ""
    uacr_value_2: Optional[float] = None

    def normalized_sex(self) -> str:
        value = self.sex.strip().lower()
        aliases = {
            "m": "male",
            "male": "male",
            "man": "male",
            "男": "male",
            "f": "female",
            "female": "female",
            "woman": "female",
            "女": "female",
        }
        return aliases.get(value, "")

    def parsed_date(self, field_name: str) -> date | None:
        return parse_clinical_date(getattr(self, field_name, ""))

    def pair_gap_days(self, date_field_1: str, date_field_2: str) -> int | None:
        first = self.parsed_date(date_field_1)
        second = self.parsed_date(date_field_2)
        if first is None or second is None:
            return None
        return abs((second - first).days)

    def pair_has_valid_interval(self, date_field_1: str, date_field_2: str, min_days: int = 90) -> bool:
        gap = self.pair_gap_days(date_field_1, date_field_2)
        return gap is not None and gap >= min_days

    def non_hdl_c(self) -> Optional[float]:
        if self.total_cholesterol is None or self.hdl_c is None:
            return None
        return self.total_cholesterol - self.hdl_c


@dataclass
class ParseResult:
    extracted_fields: dict[str, object]
    notes: list[str]
    evidence: dict[str, list[str]] = field(default_factory=dict)
    review_flags: list[str] = field(default_factory=list)


@dataclass
class RuleOutcome:
    title: str
    status: str
    summary: str
    matched_conditions: list[str]
    missing_fields: list[str]
    follow_up_notes: list[str]
    risk_category: str = ""
    ldl_start_threshold: Optional[float] = None
    non_hdl_target: Optional[float] = None
