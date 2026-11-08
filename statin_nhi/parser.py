from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .models import ParseResult, format_roc_date, parse_clinical_date
from .rules import _estimate_egfr_epi_2021


NUMBER_PATTERNS: dict[str, list[str]] = {
    "age": [
        r"(\d{1,3})\s*歲",
        r"age\s*[:：]?\s*(\d{1,3})",
        r"\b(\d{1,3})\s*-?\s*(?:y/o|yo|years?\s+old|year-old)\b",
    ],
    "total_cholesterol": [r"(?:TC|Total Chol(?:esterol)?)\s*[:：]?\s*(\d{2,3}(?:\.\d+)?)"],
    "ldl_c": [r"(?:LDL(?:-C)?)\s*[:：]?\s*(\d{2,3}(?:\.\d+)?)"],
    "hdl_c": [r"(?:HDL(?:-C)?)\s*[:：]?\s*(\d{2,3}(?:\.\d+)?)"],
    "triglycerides": [r"(?:TG|Triglyceride(?:s)?)\s*[:：]?\s*(\d{2,4}(?:\.\d+)?)"],
    "uacr": [r"(?:UACR|ALB\s*[\/∕]\s*CRE)\s*[:：]?\s*(\d{1,4}(?:\.\d+)?)"],
    "waist_cm": [
        r"(?:waist|腰圍|腹圍|\bWC\b|\bAC\b|abdominal circumference|waist measurement|waist girth|waist circumference)\s*[:：]?\s*(\d{2,3}(?:\.\d+)?)"
    ],
    "fasting_glucose": [r"(?:FBG|FBS|AC sugar|fasting blood sugar|fasting glucose|空腹血糖)\s*[:：]?\s*(\d{2,3}(?:\.\d+)?)"],
    "cac_score": [r"(?:CAC)\s*[:：]?\s*(\d{1,4}(?:\.\d+)?)"],
    "creatinine_latest": [r"(?:Cr|CRE|Creatinine)\s*[:：]?\s*(\d+(?:\.\d+)?)"],
}

EGFR_PRIORITY_PATTERNS: list[tuple[str, str]] = [
    ("eGFRcr-cys", r"(?:eGFRcr-cys)\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)"),
    ("eGFR-EPI", r"(?:eGFR(?:-|\s*)EPI)\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)"),
    ("eGFR-MDRD", r"(?:eGFR(?:-|\s*)MDRD)\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)"),
    ("eGFR", r"(?:eGFR)\s*[:：]?\s*(\d{1,3}(?:\.\d+)?)"),
]

DATE_TOKEN_PATTERN = r"(?P<date>(?<!\d)(?:\d{3,4}[/-]\d{1,2}[/-]\d{1,2}|\d{7}|\d{8})(?!\d))"
CREATININE_PATTERN = r"\b(?:Cr|CRE|Creatinine)\s*[:：]?\s*(\d+(?:\.\d+)?)"
UACR_PATTERN = r"(?:UACR|ALB\s*[\/∕]\s*CRE)\s*[:：]?\s*(\d+(?:\.\d+)?)"

BP_PATTERNS = [
    r"(\d{2,3})\s*/\s*(\d{2,3})\s*mmHg",
    r"BP\s*[:：]?\s*(\d{2,3})\s*/\s*(\d{2,3})",
]

NEGATION_PATTERNS = [r"\bno\b", r"\bdenies\b", r"\bwithout\b", r"否認", r"無", r"沒有"]
UNCERTAIN_PATTERNS = [r"\br/o\b", r"rule out", r"\bpossible\b", r"\bsuspect\b", r"\?", r"疑似", r"待排除"]
PLAN_PATTERNS = [r"\bplan\b", r"\bschedule\b", r"\barrange\b", r"\bwill\b", r"將", r"預計", r"安排", r"考慮做"]

CURRENT_SMOKING_PATTERNS = [r"\bcurrent smoker\b", r"\bactive smoker\b", r"\bcurrently smoking\b", r"\bsmoker\b", r"吸菸", r"抽菸"]
FORMER_SMOKING_PATTERNS = [r"\bex-smoker\b", r"\bformer smoker\b", r"\bquit smoking\b", r"戒菸"]
DIABETES_PATTERNS = [
    r"\bT1DM\b",
    r"\bT2DM\b",
    r"\bDM\b",
    r"diabetes mellitus",
    r"type 1 diabetes",
    r"type 2 diabetes",
    r"第一型糖尿病",
    r"第二型糖尿病",
]
DIABETES_EXCLUSION_PATTERNS = [r"hyperglycemia", r"prediabetes", r"impaired fasting glucose"]
HYPERTENSION_PATTERNS = [r"\bHTN\b", r"hypertension", r"高血壓"]

ASCVD_PATTERNS = [
    r"\bCAD\b",
    r"\bCHD\b",
    r"\bIHD\b",
    r"coronary artery disease",
    r"ischemic heart disease",
    r"冠心病",
    r"缺血性心臟病",
    r"\bangina\b",
    r"stable angina",
    r"chronic coronary syndrome",
]
ACS_PATTERNS = [
    r"\bACS\b",
    r"acute coronary syndrome",
    r"急性冠心症(?:候群)?",
    r"\bSTEMI\b",
    r"\bNSTEMI\b",
    r"\bMI\b",
    r"myocardial infarction",
    r"心肌梗塞",
    r"unstable angina",
    r"不穩定心絞痛",
]
RECENT_MI_PATTERNS = [
    r"(?:一年內|近一年|within (?:the )?(?:past )?(?:one|1) year)[^\n]{0,40}?(?:MI|myocardial infarction|心肌梗塞)",
    r"(?:MI|myocardial infarction|心肌梗塞)[^\n]{0,40}?(?:一年內|近一年|within (?:the )?(?:past )?(?:one|1) year)",
]
RECURRENT_MI_PATTERNS = [r"recurrent MI", r"multiple MI", r"多次心肌梗塞", r"反覆心肌梗塞"]
MULTIVESSEL_CORONARY_PATTERNS = [
    r"multivessel coronary",
    r"multi-vessel coronary",
    r"多支冠狀動脈阻塞",
    r"\b[23]\s*(?:-|\s*)?(?:VD|vessels?\s+disease)\b",
]
REVASC_PATTERNS = [
    r"\bs/p PCI\b",
    r"\bs/p CABG\b",
    r"\bPCI\b",
    r"\bPTCA\b",
    r"\bPOBAS?\b",
    r"\bCABG\b",
    r"\bstent\b",
    r"冠狀動脈支架",
    r"心導管介入",
    r"冠狀動脈繞道",
]
STROKE_PATTERNS = [r"\bTIA\b", r"ischemic stroke", r"cerebral infarction", r"缺血性中風", r"腦梗塞", r"暫時性腦缺血", r"\bstroke\b", r"中風"]
HEMORRHAGIC_STROKE_PATTERNS = [r"hemorrhagic stroke", r"haemorrhagic stroke", r"出血性中風", r"腦出血"]
PAD_PATTERNS = [r"\bPAD\b", r"\bPAOD\b", r"peripheral arterial disease", r"周邊動脈疾病", r"周邊血管疾病"]
LIMB_ISCHEMIA_PATTERNS = [r"limb ischemia", r"critical limb ischemia", r"acute limb ischemia", r"肢體缺血", r"下肢缺血", r"臨界肢體缺血"]
PERIPHERAL_REVASCULARIZATION_PATTERNS = [
    r"peripheral angioplasty",
    r"peripheral revascularization",
    r"lower extremity angioplasty",
    r"下肢血管再通",
    r"周邊血管再通",
    r"周邊動脈血管成形",
]
AMPUTATION_PATTERNS = [r"\bamputation\b", r"截肢"]
EARLY_CAD_FHX_PATTERNS = [r"family history of premature CAD", r"premature CAD family history", r"premature MI family history", r"早發性冠心病家族史"]
CKD_PATTERNS = [r"\bCKD\b", r"chronic kidney disease", r"慢性腎臟病", r"慢性腎病"]
AKI_PATTERNS = [r"\bAKI\b", r"acute kidney injury"]
DIALYSIS_PATTERNS = [r"\bdialysis\b", r"\bhemodialysis\b", r"\bperitoneal dialysis\b", r"洗腎", r"血液透析", r"腹膜透析"]
CAROTID_PATTERNS = [r"carotid stenosis", r"頸動脈狹窄"]
CORONARY_STENOSIS_GE_50_PATTERNS = [
    r"(?:coronary(?: artery)?|冠狀動脈)[^\n]{0,40}?(?:stenosis|narrowing|狹窄)[^\n]{0,20}?(?:50|[5-9]\d|100)\s*%",
    r"(?:50|[5-9]\d|100)\s*%[^\n]{0,40}?(?:coronary(?: artery)?|冠狀動脈)",
]
PERIPHERAL_STENOSIS_GE_50_PATTERNS = [
    r"(?:peripheral(?: artery)?|週邊動脈|周邊動脈)[^\n]{0,40}?(?:stenosis|narrowing|狹窄)[^\n]{0,20}?(?:50|[5-9]\d|100)\s*%",
    r"(?:50|[5-9]\d|100)\s*%[^\n]{0,40}?(?:peripheral(?: artery)?|週邊動脈|周邊動脈)",
]
CAROTID_STENOSIS_GE_50_PATTERNS = [
    r"(?:carotid|頸動脈)[^\n]{0,40}?(?:stenosis|narrowing|狹窄)[^\n]{0,20}?(?:50|[5-9]\d|100)\s*%",
    r"(?:50|[5-9]\d|100)\s*%[^\n]{0,40}?(?:carotid|頸動脈)",
]

BP_MED_PATTERNS = [r"antihypertensive", r"降壓藥"]
TG_MED_PATTERNS = [
    r"fibrate",
    r"fenofibrate",
    r"bezafibrate",
    r"gemfibrozil",
    r"\bGEMD\b",
    r"\bFenolip(?:-U)?\b",
    r"\bPravafen\b",
    r"降TG藥",
    r"降三酸甘油脂藥",
]
LIPID_LOWERING_MED_PATTERNS = [
    r"\bstatin\b",
    r"\b(?:atorvastatin|rosuvastatin|simvastatin|pravastatin|fluvastatin|lovastatin|pitavastatin)\b",
    r"\b(?:ezetimibe|ezetrol|atozet|crestor|tulip|lipitor|livalo|pravafen|caduet)\b",
    r"降膽固醇藥",
    r"降血脂藥",
]
STATIN_MEDICATION_PATTERNS = [
    r"\bstatin\b",
    r"\b(?:atorvastatin|rosuvastatin|simvastatin|pravastatin|fluvastatin|lovastatin|pitavastatin)\b",
    r"\b(?:atozet|crestor|tulip|lipitor|livalo|pravafen|caduet)\b",
]

ASCVD_CONTEXT_BLOCKERS = [r"\bfhx\b", r"family history", r"家族史", r"父親", r"母親"]

ICD_RULES: list[tuple[str, list[str]]] = [
    ("ascvd_history", [r"\bI2[0-5](?:\.\d+)?\b", r"\bI21\b", r"\bI22\b", r"\bI25\.2\b"]),
    ("ischemic_stroke_tia", [r"\bI63(?:\.\d+)?\b", r"\bG45(?:\.\d+)?\b"]),
    ("diabetes", [r"\bE1[0-4](?:\.\d+)?\b"]),
    ("ckd_persistent_3m", [r"\bN18(?:\.\d+)?\b"]),
]


def _window_has_blocker(window: str) -> bool:
    return any(re.search(p, window, re.IGNORECASE) for p in NEGATION_PATTERNS + UNCERTAIN_PATTERNS + PLAN_PATTERNS)


def _has_positive_keyword(
    text: str,
    patterns: list[str],
    context_blockers: list[str] | None = None,
    blockers_must_precede: bool = False,
) -> bool:
    blockers = context_blockers or []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 24)
            end = min(len(text), match.end() + 24)
            window = text[start:end]
            if _window_has_blocker(window):
                continue
            blocker_context = text[max(0, match.start() - 40) : match.start()] if blockers_must_precede else window
            if any(re.search(blocker, blocker_context, re.IGNORECASE) for blocker in blockers):
                continue
            return True
    return False


def _extract_best_egfr(text: str) -> tuple[float | None, list[str]]:
    notes: list[str] = []
    if re.search(r"(?:eGFRcys)\s*[:：]?\s*\d", text, re.IGNORECASE):
        notes.append("偵測到 eGFRcys，但依目前規則排除，不納入判讀。")
    for label, pattern in EGFR_PRIORITY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            notes.append(f"已依 eGFR 優先順序採用 {label}。")
            return float(match.group(1)), notes
    return None, notes


def _extract_sex(text: str) -> str:
    if re.search(r"\bmale\b|男性|男", text, re.IGNORECASE):
        return "male"
    if re.search(r"\bfemale\b|女性|女", text, re.IGNORECASE):
        return "female"
    return ""


def _extract_dated_labs(text: str) -> list[tuple[date, str]]:
    """Return clinical-report lines that contain a valid ROC or Gregorian date."""
    reports: list[tuple[date, str]] = []
    for line in text.splitlines():
        match = re.search(DATE_TOKEN_PATTERN, line)
        if not match:
            continue
        report_date = parse_clinical_date(match.group("date"))
        if report_date is not None:
            reports.append((report_date, line))
    return reports


def _extract_dated_lab_series(text: str, pattern: str) -> list[tuple[date, float]]:
    values: dict[date, float] = {}
    for report_date, line in _extract_dated_labs(text):
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            values[report_date] = float(match.group(1))
    return sorted(values.items())


def _extract_dated_egfr_series(text: str) -> tuple[list[tuple[date, float]], list[str]]:
    values: dict[date, float] = {}
    notes: list[str] = []
    for report_date, line in _extract_dated_labs(text):
        for label, pattern in EGFR_PRIORITY_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                values[report_date] = float(match.group(1))
                notes.append(f"{format_roc_date(report_date)} 已依 eGFR 優先順序採用 {label}。")
                break
    return sorted(values.items()), notes


@dataclass(frozen=True)
class _RenalObservation:
    report_date: date
    kind: str
    value: float
    egfr_type: str = ""
    panel_id: str = ""


def _canonical_renal_label(value: str) -> tuple[str, str] | None:
    """Classify renal lab labels while preserving the reported eGFR equation."""
    compact = re.sub(r"\s+", "", value).lower().replace("∕", "/")
    if compact == "egfrcr-cys":
        return "egfr", "eGFRcr-cys"
    if compact in {"egfr-epi", "egfrepi"}:
        return "egfr", "eGFR-EPI"
    if compact in {"egfr-mdrd", "egfrmdrd"}:
        return "egfr", "eGFR-MDRD"
    if compact == "egfr":
        return "egfr", "eGFR"
    if compact == "egfrcys":
        return None
    if compact in {"cr", "cre", "creatinine"}:
        # Retain the original label. In urine panels, the hospital export uses
        # CRE; a clinical-note Cr remains eligible as blood creatinine.
        return "creatinine", compact
    if compact in {"uacr", "alb/cre"}:
        return "uacr", ""
    return None


def _number_from_cell(value: str) -> float | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:\([A-Za-z]+\))?\s*", value)
    return float(match.group(1)) if match else None


def _extract_history_table_observations(text: str) -> list[_RenalObservation]:
    """Read tabular historical reports whose dates occupy the column headings."""
    observations: list[_RenalObservation] = []
    lines = text.splitlines()
    for header_index, header in enumerate(lines):
        header_cells = header.split("\t")
        date_columns = [
            (index, parsed)
            for index, cell in enumerate(header_cells)
            if (parsed := parse_clinical_date(cell.strip())) is not None
        ]
        if len(date_columns) < 2:
            continue

        panel_id = f"history-{header_index}"
        for row in lines[header_index + 1 :]:
            if not row.strip():
                break
            cells = row.split("\t")
            label = cells[0].strip() if cells else ""
            classified = _canonical_renal_label(label)
            if classified is None:
                if any(parse_clinical_date(cell.strip()) for cell in cells):
                    break
                continue
            kind, egfr_type = classified
            for column, report_date in date_columns:
                if column >= len(cells):
                    continue
                value = _number_from_cell(cells[column])
                if value is not None:
                    observations.append(_RenalObservation(report_date, kind, value, egfr_type, panel_id))
    return observations


def _extract_single_report_observations(text: str) -> list[_RenalObservation]:
    """Read report rows that inherit their date from the preceding dated row."""
    observations: list[_RenalObservation] = []
    current_date: date | None = None
    current_panel = ""
    panel_number = 0
    panel_has_egfr = False

    for line_index, line in enumerate(text.splitlines()):
        if "\t" not in line:
            continue
        cells = [cell.strip() for cell in line.split("\t")]
        explicit_date = next((parsed for cell in cells if (parsed := parse_clinical_date(cell)) is not None), None)
        label_index = next(
            (index for index, cell in enumerate(cells) if _canonical_renal_label(cell) is not None),
            None,
        )
        if label_index is None:
            continue
        kind, egfr_type = _canonical_renal_label(cells[label_index]) or ("", "")
        if explicit_date is not None:
            starts_new_panel = explicit_date != current_date or (panel_has_egfr and kind in {"creatinine", "uacr"})
            if starts_new_panel:
                panel_number += 1
                current_panel = f"single-{line_index}-{panel_number}"
                panel_has_egfr = False
            current_date = explicit_date
        if current_date is None:
            continue
        value = next((_number_from_cell(cell) for cell in cells[label_index + 1 :] if _number_from_cell(cell) is not None), None)
        if value is None:
            continue
        observations.append(_RenalObservation(current_date, kind, value, egfr_type, current_panel))
        if kind == "egfr":
            panel_has_egfr = True
    return observations


def _extract_inline_renal_observations(text: str) -> list[_RenalObservation]:
    """Read dated order and summary lines, where results appear alongside labels."""
    observations: list[_RenalObservation] = []
    labelled_value = re.compile(
        r"(?P<label>eGFRcr-cys|eGFR(?:[-\s]*(?:EPI|MDRD))?|eGFRcys|UACR|ALB\s*[\/∕]\s*CRE|Cr|CRE|Creatinine)"
        r"\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for line_index, line in enumerate(text.splitlines()):
        if "\t" in line:
            # Tabular reports are handled separately so their inherited date and
            # urine-versus-blood specimen context remain intact.
            continue
        date_match = re.search(DATE_TOKEN_PATTERN, line)
        if not date_match:
            continue
        report_date = parse_clinical_date(date_match.group("date"))
        if report_date is None:
            continue
        panel_id = f"inline-{line_index}"
        for match in labelled_value.finditer(line):
            classified = _canonical_renal_label(match.group("label"))
            if classified is None:
                continue
            kind, egfr_type = classified
            observations.append(_RenalObservation(report_date, kind, float(match.group("value")), egfr_type, panel_id))
    return observations


def _extract_renal_observations(text: str) -> list[_RenalObservation]:
    """Collect renal results and discard creatinine from urine-albumin panels."""
    observations = (
        _extract_history_table_observations(text)
        + _extract_single_report_observations(text)
        + _extract_inline_renal_observations(text)
    )
    panel_kinds: dict[str, set[str]] = {}
    for observation in observations:
        panel_kinds.setdefault(observation.panel_id, set()).add(observation.kind)

    filtered = [
        observation
        for observation in observations
        if not (
            observation.kind == "creatinine"
            and observation.egfr_type == "cre"
            and "uacr" in panel_kinds.get(observation.panel_id, set())
            and "egfr" not in panel_kinds.get(observation.panel_id, set())
        )
    ]
    return list(dict.fromkeys(filtered))


def _renal_series_from_observations(
    observations: list[_RenalObservation],
) -> tuple[dict[str, list[tuple[date, float]]], list[tuple[date, float]], list[tuple[date, float]]]:
    egfr_values: dict[str, dict[date, float]] = {label: {} for label, _pattern in EGFR_PRIORITY_PATTERNS}
    creatinine_values: dict[date, float] = {}
    uacr_values: dict[date, float] = {}
    for observation in observations:
        if observation.kind == "egfr":
            egfr_values[observation.egfr_type][observation.report_date] = observation.value
        elif observation.kind == "creatinine":
            creatinine_values[observation.report_date] = observation.value
        elif observation.kind == "uacr":
            uacr_values[observation.report_date] = observation.value
    return (
        {label: sorted(values.items()) for label, values in egfr_values.items()},
        sorted(creatinine_values.items()),
        sorted(uacr_values.items()),
    )


def _select_latest_direct_egfr(
    series_by_type: dict[str, list[tuple[date, float]]],
) -> tuple[str, list[tuple[date, float]]]:
    """Choose the latest direct eGFR, applying equation priority only on that date."""
    all_dates = [report_date for series in series_by_type.values() for report_date, _value in series]
    if not all_dates:
        return "", []
    latest_date = max(all_dates)
    for label, _pattern in EGFR_PRIORITY_PATTERNS:
        series = series_by_type.get(label, [])
        if any(report_date == latest_date for report_date, _value in series):
            return label, series
    return "", []


def _set_pair_fields(
    extracted_fields: dict[str, object],
    evidence: dict[str, list[str]],
    prefix: str,
    series: list[tuple[date, float]],
    source: str,
) -> None:
    """Populate the two latest dated reports, preserving chronological order."""
    if not series:
        return
    selected = series[-2:]
    for index, (report_date, value) in enumerate(selected, start=3 - len(selected)):
        date_text = format_roc_date(report_date)
        extracted_fields[f"{prefix}_date_{index}"] = date_text
        extracted_fields[f"{prefix}_value_{index}"] = value
        _append_evidence(evidence, f"{prefix}_value_{index}", f"{date_text} {source} = {value:g}")


def _series_has_persistent_threshold(series: list[tuple[date, float]], threshold) -> bool:
    """Whether the two most recent dated reports meet a CKD threshold for 90 days."""
    if len(series) < 2:
        return False
    first_date, first_value = series[-2]
    second_date, second_value = series[-1]
    return abs((second_date - first_date).days) >= 90 and threshold(first_value) and threshold(second_value)


def _select_chronic_pair(series: list[tuple[date, float]], min_days: int = 90) -> list[tuple[date, float]]:
    """Select the latest report and the nearest report at least ``min_days`` earlier."""
    if not series:
        return []
    latest = series[-1]
    for candidate in reversed(series[:-1]):
        if (latest[0] - candidate[0]).days >= min_days:
            return [candidate, latest]
    return [latest]


def _apply_icd_rules(text: str, extracted_fields: dict[str, object]) -> None:
    for field_name, patterns in ICD_RULES:
        if field_name == "ascvd_history":
            if _has_positive_keyword(text, patterns, ASCVD_CONTEXT_BLOCKERS, blockers_must_precede=True):
                extracted_fields[field_name] = True
        elif _has_positive_keyword(text, patterns):
            extracted_fields[field_name] = True


def _append_evidence(evidence: dict[str, list[str]], field_name: str, message: str) -> None:
    evidence.setdefault(field_name, [])
    if message not in evidence[field_name]:
        evidence[field_name].append(message)


def parse_note(
    text: str,
    fallback_sex: str = "",
    fallback_age: float | None = None,
) -> ParseResult:
    extracted_fields: dict[str, object] = {}
    notes: list[str] = []
    evidence: dict[str, list[str]] = {}
    review_flags: list[str] = []

    if not text.strip():
        return ParseResult(extracted_fields=extracted_fields, notes=notes, evidence=evidence, review_flags=review_flags)

    sex = _extract_sex(text) or fallback_sex.strip().lower()
    if sex in {"男", "m"}:
        sex = "male"
    elif sex in {"女", "f"}:
        sex = "female"
    if sex:
        extracted_fields["sex"] = sex
        _append_evidence(evidence, "sex", f"病歷文字提供性別：{sex}")

    age_patterns = NUMBER_PATTERNS["age"]
    for pattern in age_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_fields["age"] = float(match.group(1))
            _append_evidence(evidence, "age", f"病歷文字擷取 age = {float(match.group(1)):g}")
            break
    if "age" not in extracted_fields and fallback_age is not None:
        extracted_fields["age"] = fallback_age
        _append_evidence(evidence, "age", f"使用表單輸入年齡 = {fallback_age:g}")

    egfr_value, egfr_notes = _extract_best_egfr(text)
    notes.extend(egfr_notes)
    if egfr_value is not None:
        extracted_fields["egfr"] = egfr_value
        _append_evidence(evidence, "egfr", f"病歷文字擷取 eGFR = {egfr_value:g}")

    for field_name, patterns in NUMBER_PATTERNS.items():
        if field_name in {"age", "creatinine_latest"}:
            # Creatinine requires renal-panel context to avoid accepting urine
            # creatinine from ALB/CRE or protein/creatinine reports.
            continue
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_fields[field_name] = float(match.group(1))
                _append_evidence(evidence, field_name, f"病歷文字擷取 {field_name} = {float(match.group(1)):g}")
                break

    for pattern in BP_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_fields["systolic_bp"] = float(match.group(1))
            extracted_fields["diastolic_bp"] = float(match.group(2))
            _append_evidence(evidence, "systolic_bp", f"病歷文字擷取收縮壓 = {float(match.group(1)):g}")
            _append_evidence(evidence, "diastolic_bp", f"病歷文字擷取舒張壓 = {float(match.group(2)):g}")
            break

    if _has_positive_keyword(text, CURRENT_SMOKING_PATTERNS) and not _has_positive_keyword(text, FORMER_SMOKING_PATTERNS):
        extracted_fields["smoking"] = True
        _append_evidence(evidence, "smoking", "命中目前吸菸關鍵字")
    if _has_positive_keyword(text, DIABETES_PATTERNS) and not _has_positive_keyword(text, DIABETES_EXCLUSION_PATTERNS):
        extracted_fields["diabetes"] = True
        _append_evidence(evidence, "diabetes", "命中糖尿病診斷關鍵字")

    keyword_map: dict[str, tuple[list[str], list[str]]] = {
        "hypertension": (HYPERTENSION_PATTERNS + BP_MED_PATTERNS, []),
        "ascvd_history": (ASCVD_PATTERNS, ASCVD_CONTEXT_BLOCKERS),
        "acute_coronary_syndrome": (ACS_PATTERNS, []),
        "recent_mi_within_1y": (RECENT_MI_PATTERNS, []),
        "recurrent_mi": (RECURRENT_MI_PATTERNS, []),
        "multivessel_coronary_disease": (MULTIVESSEL_CORONARY_PATTERNS, []),
        "coronary_revascularization": (REVASC_PATTERNS, []),
        "ischemic_stroke_tia": (STROKE_PATTERNS, HEMORRHAGIC_STROKE_PATTERNS),
        "family_history_early_cad": (EARLY_CAD_FHX_PATTERNS, []),
        "on_tg_medication": (TG_MED_PATTERNS, []),
        "on_lipid_lowering_medication": (LIPID_LOWERING_MED_PATTERNS, []),
        "on_statin_medication": (STATIN_MEDICATION_PATTERNS, []),
        "carotid_stenosis": (CAROTID_PATTERNS, []),
        "coronary_stenosis_ge_50": (CORONARY_STENOSIS_GE_50_PATTERNS, []),
        "peripheral_stenosis_ge_50": (PERIPHERAL_STENOSIS_GE_50_PATTERNS, []),
        "carotid_stenosis_ge_50": (CAROTID_STENOSIS_GE_50_PATTERNS, []),
    }

    for field_name, (patterns, blockers) in keyword_map.items():
        if _has_positive_keyword(text, patterns, blockers, blockers_must_precede=field_name == "ascvd_history"):
            extracted_fields[field_name] = True
            _append_evidence(evidence, field_name, f"命中 {field_name} 關鍵字")

    if any(extracted_fields.get(field_name) for field_name in ("recent_mi_within_1y", "recurrent_mi")):
        extracted_fields["acute_coronary_syndrome"] = True
        _append_evidence(evidence, "acute_coronary_syndrome", "由心肌梗塞條件推定急性冠心症病史")

    has_pad = _has_positive_keyword(text, PAD_PATTERNS) or _has_positive_keyword(
        text, [r"\bI70\.2\b", r"\bI73\.9\b", r"\bI74(?:\.\d+)?\b"]
    )
    has_pad_qualifier = any(
        _has_positive_keyword(text, patterns)
        for patterns in (LIMB_ISCHEMIA_PATTERNS, PERIPHERAL_REVASCULARIZATION_PATTERNS, AMPUTATION_PATTERNS)
    )
    if has_pad and has_pad_qualifier:
        extracted_fields["peripheral_arterial_disease"] = True
        _append_evidence(evidence, "peripheral_arterial_disease", "PAD 合併肢體缺血、周邊血管再通術或截肢證據")
    elif has_pad:
        notes.append("病歷提到 PAD／PAOD，但缺少肢體缺血、周邊血管再通術或截肢證據，不直接算周邊動脈疾病。")
        review_flags.append("PAD／PAOD 缺少合格肢體缺血或處置證據。")

    if any(
        extracted_fields.get(field_name)
        for field_name in (
            "recent_mi_within_1y",
            "recurrent_mi",
            "multivessel_coronary_disease",
            "acute_coronary_syndrome",
            "coronary_revascularization",
            "coronary_stenosis_ge_50",
        )
    ):
        extracted_fields["ascvd_history"] = True
        _append_evidence(evidence, "ascvd_history", "由冠狀動脈急性事件、介入治療或狹窄條件推定 CAD")
    if extracted_fields.get("carotid_stenosis_ge_50"):
        extracted_fields["carotid_stenosis"] = True
        _append_evidence(evidence, "carotid_stenosis", "由頸動脈狹窄 >= 50% 推定頸動脈狹窄")
    if any(extracted_fields.get(field_name) for field_name in ("coronary_stenosis_ge_50", "peripheral_stenosis_ge_50", "carotid_stenosis_ge_50")):
        extracted_fields["arterial_stenosis_ge_50"] = True
        _append_evidence(evidence, "arterial_stenosis_ge_50", "由特定血管狹窄 >= 50% 推定")

    if _has_positive_keyword(text, CKD_PATTERNS) and not _has_positive_keyword(text, AKI_PATTERNS):
        extracted_fields["ckd_persistent_3m"] = True
        _append_evidence(evidence, "ckd_persistent_3m", "命中 CKD 關鍵字且未命中 AKI 排除詞")
    if _has_positive_keyword(text, DIALYSIS_PATTERNS):
        extracted_fields["on_dialysis"] = True
        _append_evidence(evidence, "on_dialysis", "命中正在接受透析／洗腎關鍵字")

    _apply_icd_rules(text, extracted_fields)
    for field_name in ("ascvd_history", "ischemic_stroke_tia", "peripheral_arterial_disease", "diabetes", "ckd_persistent_3m"):
        if field_name in extracted_fields and not evidence.get(field_name):
            _append_evidence(evidence, field_name, f"命中 {field_name} 對應 ICD-10")

    renal_observations = _extract_renal_observations(text)
    egfr_series_by_type, creatinine_series, dated_uacr_series = _renal_series_from_observations(renal_observations)
    if creatinine_series:
        latest_date, latest_value = creatinine_series[-1]
        latest_date_text = format_roc_date(latest_date)
        extracted_fields["creatinine_latest"] = latest_value
        extracted_fields["creatinine_latest_date"] = latest_date_text
        _append_evidence(evidence, "creatinine_latest", f"病歷文字擷取最新 creatinine = {latest_value:g} ({latest_date_text})")
        creatinine_pair = _select_chronic_pair(creatinine_series)
        if len(creatinine_pair) == 2:
            past_date, past_value = creatinine_pair[0]
            past_date_text = format_roc_date(past_date)
            extracted_fields["creatinine_past"] = past_value
            extracted_fields["creatinine_past_date"] = past_date_text
            _append_evidence(evidence, "creatinine_past", f"病歷文字擷取較早 creatinine = {past_value:g} ({past_date_text})")
    elif "creatinine_latest" in extracted_fields:
        _append_evidence(evidence, "creatinine_latest", f"病歷文字擷取 creatinine = {float(extracted_fields['creatinine_latest']):g}")

    selected_uacr_series = _select_chronic_pair(dated_uacr_series)
    _set_pair_fields(extracted_fields, evidence, "uacr", selected_uacr_series, "UACR")

    age_value = extracted_fields.get("age")
    sex_value = extracted_fields.get("sex")
    age_for_egfr = float(age_value) if isinstance(age_value, (int, float)) else None
    sex_for_egfr = sex_value if isinstance(sex_value, str) else ""
    direct_egfr_type, direct_egfr_series = _select_latest_direct_egfr(egfr_series_by_type)
    selected_direct_egfr = _select_chronic_pair(direct_egfr_series)
    estimated_egfr_series: list[tuple[date, float]] = []
    if age_for_egfr is not None and sex_for_egfr:
        for report_date, creatinine in creatinine_series:
            estimated = _estimate_egfr_epi_2021(creatinine, age_for_egfr, sex_for_egfr)
            if estimated is not None:
                estimated_egfr_series.append((report_date, round(estimated, 1)))
    selected_estimated_egfr = _select_chronic_pair(estimated_egfr_series)

    # A chronic pair must use the same reported equation. If that cannot be
    # established, fall back to two creatinine-derived eGFR-EPI values instead.
    if len(selected_direct_egfr) == 2:
        selected_egfr_series = selected_direct_egfr
        renal_egfr_series = direct_egfr_series
        egfr_source = direct_egfr_type
        notes.append(f"已採用 {direct_egfr_type} 的同類型 eGFR 兩次資料判讀。")
    elif estimated_egfr_series:
        selected_egfr_series = selected_estimated_egfr
        renal_egfr_series = estimated_egfr_series
        egfr_source = "creatinine"
        notes.append("直接 eGFR 缺少同類型且相隔至少 3 個月的資料，已改用 creatinine 推算 eGFR-EPI。")
    else:
        selected_egfr_series = selected_direct_egfr
        renal_egfr_series = direct_egfr_series
        egfr_source = direct_egfr_type

    creatinine_by_date = dict(creatinine_series)
    derived_creatinine_unstable = (
        len(selected_egfr_series) == 2
        and egfr_source == "creatinine"
        and abs(creatinine_by_date[selected_egfr_series[1][0]] - creatinine_by_date[selected_egfr_series[0][0]]) > 0.5
    )
    if derived_creatinine_unstable:
        notes.append("兩次 creatinine 相差超過 0.5 mg/dL，推算 eGFR 不直接作為 CKD 的兩次證據。")
        review_flags.append("creatinine 變動過大，需排除 AKI 後再判斷 CKD。")
    else:
        _set_pair_fields(extracted_fields, evidence, "egfr", selected_egfr_series, "eGFR")
    if renal_egfr_series:
        latest_egfr_date, latest_egfr = renal_egfr_series[-1]
        extracted_fields["egfr"] = latest_egfr
        extracted_fields["egfr_date"] = format_roc_date(latest_egfr_date)
        source_label = "推算 eGFR-EPI" if egfr_source == "creatinine" else egfr_source
        extracted_fields["egfr_source"] = egfr_source
        _append_evidence(evidence, "egfr", f"病歷文字擷取最新 {source_label} = {latest_egfr:g}")

    if not extracted_fields.get("on_dialysis") and (
        (not derived_creatinine_unstable and _series_has_persistent_threshold(selected_egfr_series, lambda value: value < 60))
        or _series_has_persistent_threshold(selected_uacr_series, lambda value: value >= 30)
    ):
        extracted_fields["ckd_persistent_3m"] = True
        _append_evidence(evidence, "ckd_persistent_3m", "兩次 eGFR 或 UACR 均達 CKD 門檻，且相隔至少 90 天")

    if not extracted_fields:
        notes.append("無法從病歷文字擷取可用欄位，請改用手動輸入。")
    else:
        notes.append("已從病歷文字擷取可用欄位，請人工確認後判讀。")

    if "ldl_c" not in extracted_fields and "total_cholesterol" not in extracted_fields:
        notes.append("缺少 LDL-C 或 TC，部分規則可能無法完整判讀。")
    if "triglycerides" not in extracted_fields:
        notes.append("缺少 TG，代謝症候群相關判讀可能無法完整進行。")
    if "fasting_glucose" not in extracted_fields and re.search(r"\bglucose\b", text, re.IGNORECASE):
        notes.append("病歷只出現一般 glucose，依目前規則不自動視為空腹血糖。")
        review_flags.append("只有一般 glucose，不自動視為空腹血糖。")
    if "creatinine_latest" in extracted_fields and "egfr" not in extracted_fields:
        notes.append("有抓到 creatinine，但缺少年齡或性別，暫時無法自動推算 eGFR-EPI。")
        review_flags.append("只有 creatinine、但缺少年齡或性別，無法自動推算 eGFR-EPI。")
    if re.search(r"\bFHx CAD\b|父親心臟病", text, re.IGNORECASE):
        notes.append("病歷提到家族心臟病，但未載明早發年齡，暫不直接算早發冠心病家族史。")
        review_flags.append("家族史缺少發病年齡，不直接算早發冠心病家族史。")
    if re.search(r"\bsmoking history\b|\btobacco use\b", text, re.IGNORECASE) and "smoking" not in extracted_fields:
        notes.append("病歷提到吸菸史，但目前吸菸狀態不明，需人工確認。")
        review_flags.append("吸菸狀態不明，需人工確認。")
    if re.search(r"moderate stenosis|plaque|calcification|atherosclerosis", text, re.IGNORECASE):
        notes.append("若病歷只寫 moderate stenosis / plaque / calcification / atherosclerosis，不能直接視為動脈狹窄 >= 50%。")
        review_flags.append("狹窄描述缺少明確百分比，需人工確認。")

    return ParseResult(
        extracted_fields=extracted_fields,
        notes=notes,
        evidence=evidence,
        review_flags=review_flags,
    )
