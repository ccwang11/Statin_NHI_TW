from __future__ import annotations

from .models import PatientData, RuleOutcome


NEW_RULE_THRESHOLDS = {
    "extreme": {"label": "新制極高風險", "ldl_threshold": 55, "non_hdl_threshold": 85},
    "very_high": {"label": "新制非常高風險", "ldl_threshold": 70, "non_hdl_threshold": 100},
    "high": {"label": "新制高風險", "ldl_threshold": 100, "non_hdl_threshold": 130},
    "moderate": {"label": "新制中風險", "ldl_threshold": 115, "non_hdl_threshold": 145},
    "low": {"label": "新制低風險", "ldl_threshold": 130, "non_hdl_threshold": 160},
    "minimal": {"label": "新制零危險因子", "ldl_threshold": 160, "non_hdl_threshold": None},
}


def _pair_missing(date_1: str, value_1: object, date_2: str, value_2: object, label: str) -> list[str]:
    missing: list[str] = []
    if not date_1:
        missing.append(f"{label} 第1次日期")
    if value_1 in (None, ""):
        missing.append(f"{label} 第1次數值")
    if not date_2:
        missing.append(f"{label} 第2次日期")
    if value_2 in (None, ""):
        missing.append(f"{label} 第2次數值")
    return missing


def _pair_interval_notes(patient: PatientData, date_field_1: str, date_field_2: str, label: str) -> tuple[bool, list[str], list[str]]:
    missing: list[str] = []
    notes: list[str] = []
    if not getattr(patient, date_field_1) or not getattr(patient, date_field_2):
        missing.extend([f"{label} 第1次日期", f"{label} 第2次日期"])
        return False, notes, missing
    gap = patient.pair_gap_days(date_field_1, date_field_2)
    if gap is None:
        notes.append(f"{label} 日期格式需為 YYYY-MM-DD。")
        return False, notes, missing
    if gap < 90:
        notes.append(f"{label} 兩次報告只相隔 {gap} 天，未達至少 3 個月。")
        return False, notes, missing
    return True, notes, missing


def _pair_threshold(
    patient: PatientData,
    *,
    date_field_1: str,
    value_field_1: str,
    date_field_2: str,
    value_field_2: str,
    label: str,
    comparator,
    threshold_text: str,
) -> tuple[bool, list[str], list[str], list[str]]:
    matched: list[str] = []
    notes: list[str] = []
    missing = _pair_missing(
        getattr(patient, date_field_1),
        getattr(patient, value_field_1),
        getattr(patient, date_field_2),
        getattr(patient, value_field_2),
        label,
    )
    if missing:
        return False, matched, notes, missing

    valid_interval, interval_notes, interval_missing = _pair_interval_notes(patient, date_field_1, date_field_2, label)
    notes.extend(interval_notes)
    missing.extend(interval_missing)
    if not valid_interval:
        return False, matched, notes, missing

    value_1 = getattr(patient, value_field_1)
    value_2 = getattr(patient, value_field_2)
    if comparator(value_1) and comparator(value_2):
        matched.append(f"{label} 兩次報告都符合 {threshold_text}")
        return True, matched, notes, missing

    notes.append(f"{label} 需要兩次相隔至少 3 個月的報告，而且兩次都要符合 {threshold_text}。")
    return False, matched, notes, missing


def _has_low_hdl(patient: PatientData) -> tuple[bool, list[str], list[str], list[str]]:
    sex = patient.normalized_sex()
    if patient.hdl_c is None:
        return False, [], [], ["HDL-C"]
    if sex == "male":
        if patient.hdl_c < 40:
            return True, ["HDL-C 男性 < 40"], [], []
        return False, [], ["HDL-C 未達男性低 HDL-C 門檻。"], []
    if sex == "female":
        if patient.hdl_c < 50:
            return True, ["HDL-C 女性 < 50"], [], []
        return False, [], ["HDL-C 未達女性低 HDL-C 門檻。"], []
    return False, [], ["低 HDL-C 需要明確性別。"], ["性別"]


def _has_coronary_disease(patient: PatientData) -> bool:
    return any(
        [
            patient.ascvd_history,
            patient.acute_coronary_syndrome,
            patient.coronary_revascularization,
            patient.recent_mi_within_1y,
            patient.recurrent_mi,
            patient.multivessel_coronary_disease,
            patient.coronary_stenosis_ge_50,
        ]
    )


def _estimate_egfr_epi_2021(creatinine: float, age: float, sex: str) -> float | None:
    normalized_sex = sex.strip().lower()
    if creatinine <= 0 or age <= 0:
        return None
    if normalized_sex == "female":
        kappa = 0.7
        alpha = -0.241
        sex_factor = 1.012
    elif normalized_sex == "male":
        kappa = 0.9
        alpha = -0.302
        sex_factor = 1.0
    else:
        return None
    scr_ratio = creatinine / kappa
    min_part = min(scr_ratio, 1) ** alpha
    max_part = max(scr_ratio, 1) ** -1.2
    age_part = 0.9938 ** age
    return 142 * min_part * max_part * age_part * sex_factor


def _selected_egfr(patient: PatientData) -> tuple[float | None, list[str], list[str]]:
    notes: list[str] = []
    missing: list[str] = []
    if patient.creatinine_latest is None:
        missing.append("eGFR 或 creatinine")
        return None, notes, missing
    if patient.age is None:
        missing.append("年齡")
    if not patient.normalized_sex():
        missing.append("性別")
    if missing:
        notes.append("若要由 creatinine 推算 eGFR-EPI，需補年齡與性別。")
        return None, notes, missing
    estimated = _estimate_egfr_epi_2021(patient.creatinine_latest, patient.age, patient.normalized_sex())
    if estimated is not None:
        notes.append("缺少直接 eGFR 報告時，已用最近一次 creatinine 推算 eGFR-EPI。")
    return estimated, notes, []


def _has_persistent_ckd_by_proposal(patient: PatientData) -> tuple[bool, list[str], list[str], list[str]]:
    matched: list[str] = []
    notes: list[str] = []
    missing: list[str] = []

    if patient.on_dialysis:
        notes.append("病歷顯示正在接受透析／洗腎，不符合進入透析前慢性腎臟病條件。")
        return False, matched, notes, missing

    if patient.ckd_persistent_3m:
        matched.append("進入透析前的慢性腎臟病 (eGFR<60 或 UACR>=30 至少三個月)")
        return True, matched, notes, missing

    egfr_pair_ok, egfr_pair_matches, egfr_pair_notes, egfr_pair_missing = _pair_threshold(
        patient,
        date_field_1="egfr_date_1",
        value_field_1="egfr_value_1",
        date_field_2="egfr_date_2",
        value_field_2="egfr_value_2",
        label="eGFR",
        comparator=lambda value: value is not None and value < 60,
        threshold_text="eGFR < 60",
    )
    matched.extend(egfr_pair_matches)
    notes.extend(egfr_pair_notes)
    missing.extend(egfr_pair_missing)
    if egfr_pair_ok:
        return True, matched, notes, missing

    uacr_pair_ok, uacr_pair_matches, uacr_pair_notes, uacr_pair_missing = _pair_threshold(
        patient,
        date_field_1="uacr_date_1",
        value_field_1="uacr_value_1",
        date_field_2="uacr_date_2",
        value_field_2="uacr_value_2",
        label="UACR",
        comparator=lambda value: value is not None and value >= 30,
        threshold_text="UACR >= 30",
    )
    matched.extend(uacr_pair_matches)
    notes.extend(uacr_pair_notes)
    missing.extend(uacr_pair_missing)
    if uacr_pair_ok:
        return True, matched, notes, missing

    egfr_value, egfr_notes, egfr_missing = _selected_egfr(patient)
    notes.extend(egfr_notes)
    missing.extend(egfr_missing)
    if egfr_value is None:
        return False, matched, notes, sorted(set(missing))

    if patient.creatinine_past is None:
        notes.append("若沒有兩次 eGFR / UACR，至少還需要另一筆較早 creatinine 佐證 CKD 時間軸。")
        missing.append("較早 creatinine")
        return False, matched, notes, sorted(set(missing))
    if patient.creatinine_month_gap is None:
        missing.append("兩次 creatinine 間隔月數")
        notes.append("缺少兩次 creatinine 的間隔資訊。")
        return False, matched, notes, sorted(set(missing))
    if patient.creatinine_month_gap < 3:
        notes.append("兩次 creatinine 間隔未達 3 個月。")
        return False, matched, notes, sorted(set(missing))
    if abs(patient.creatinine_latest - patient.creatinine_past) > 0.5:
        notes.append("兩次 creatinine 相差超過 0.5 mg/dL，需警覺 AKI，不能直接當作 CKD 證據。")
        return False, matched, notes, sorted(set(missing))
    if egfr_value < 60:
        matched.append("以 creatinine 推算 eGFR-EPI < 60，且兩次 creatinine 相隔至少 3 個月")
        return True, matched, notes, sorted(set(missing))
    return False, matched, notes, sorted(set(missing))


def _metabolic_syndrome_components(patient: PatientData) -> tuple[int, list[str], list[str], list[str]]:
    sex = patient.normalized_sex()
    components = 0
    matched: list[str] = []
    notes: list[str] = []
    missing: list[str] = []

    if sex:
        if patient.waist_cm is not None and ((sex == "male" and patient.waist_cm >= 90) or (sex == "female" and patient.waist_cm >= 80)):
            components += 1
            matched.append("腹圍符合代謝症候群門檻")
        elif patient.waist_cm is None:
            missing.append("腹圍")
        else:
            notes.append("腹圍未達代謝症候群門檻。")
    else:
        missing.append("性別")
        notes.append("腹圍門檻需要明確性別。")

    if patient.hypertension:
        components += 1
        matched.append("高血壓勾選，血壓項目符合")
    elif (patient.systolic_bp is not None and patient.systolic_bp >= 130) or (patient.diastolic_bp is not None and patient.diastolic_bp >= 85):
        components += 1
        matched.append("血壓符合代謝症候群門檻")
    elif patient.systolic_bp is None and patient.diastolic_bp is None:
        missing.append("血壓")
    else:
        notes.append("血壓未達代謝症候群門檻。")

    if patient.diabetes:
        components += 1
        matched.append("糖尿病勾選，空腹血糖項目符合")
    elif patient.fasting_glucose is not None and patient.fasting_glucose >= 100:
        components += 1
        matched.append("空腹血糖 >= 100 mg/dL")
    elif patient.fasting_glucose is None:
        missing.append("空腹血糖")
    else:
        notes.append("空腹血糖未達代謝症候群門檻。")

    if patient.on_tg_medication:
        components += 1
        matched.append("高 TG 已用藥")
    elif patient.triglycerides is not None and patient.triglycerides >= 150:
        components += 1
        matched.append("空腹 TG >= 150 mg/dL")
    elif patient.triglycerides is None:
        missing.append("空腹 TG")
    else:
        notes.append("空腹 TG 未達代謝症候群門檻。")

    hdl_ok, hdl_matches, hdl_notes, hdl_missing = _has_low_hdl(patient)
    if hdl_ok:
        components += 1
        matched.extend(hdl_matches)
    else:
        notes.extend(hdl_notes)
        missing.extend(hdl_missing)

    return components, matched, notes, sorted(set(missing))


def _new_risk_factor_count(patient: PatientData) -> tuple[int, list[str], list[str], list[str]]:
    sex = patient.normalized_sex()
    count = 0
    matched: list[str] = []
    notes: list[str] = []
    missing: list[str] = []

    if patient.hypertension:
        count += 1
        matched.append("高血壓")
    if patient.smoking:
        count += 1
        matched.append("抽菸")
    if (sex == "male" and (patient.age or 0) >= 45) or (sex == "female" and (patient.age or 0) >= 55):
        count += 1
        matched.append("男性 >= 45 歲" if sex == "male" else "女性 >= 55 歲")
    elif patient.age is None:
        missing.append("年齡")
    if patient.family_history_early_cad:
        count += 1
        matched.append("早發性冠心病家族史")

    hdl_ok, hdl_matches, hdl_notes, hdl_missing = _has_low_hdl(patient)
    if hdl_ok:
        count += 1
        matched.extend(hdl_matches)
    else:
        notes.extend(hdl_notes)
        missing.extend(hdl_missing)

    metabolic_count, metabolic_matches, metabolic_notes, metabolic_missing = _metabolic_syndrome_components(patient)
    if patient.metabolic_syndrome:
        count += 1
        matched.append("代謝症候群")
    elif metabolic_count >= 3:
        count += 1
        matched.append("代謝症候群")
    notes.extend(metabolic_notes)
    missing.extend(metabolic_missing)

    return count, matched, notes, sorted(set(missing))


def _requires_lifestyle_trial(category_key: str) -> bool:
    return category_key in {"moderate", "low", "minimal"}


def _resolve_new_risk_category(patient: PatientData) -> tuple[str, list[str], list[str], list[str], bool]:
    notes: list[str] = []
    missing: list[str] = []
    review_needed = False

    extreme_matches: list[str] = []
    if patient.recent_mi_within_1y:
        extreme_matches.append("一年內曾經歷心肌梗塞")
    if patient.recurrent_mi:
        extreme_matches.append("多次心肌梗塞病史")
    if patient.multivessel_coronary_disease:
        extreme_matches.append("多支冠狀動脈阻塞")
    acute_coronary_syndrome = any(
        [patient.acute_coronary_syndrome, patient.recent_mi_within_1y, patient.recurrent_mi]
    )
    if acute_coronary_syndrome and patient.diabetes:
        extreme_matches.append("急性冠心症合併糖尿病")

    coronary_disease = _has_coronary_disease(patient)
    carotid_disease = patient.carotid_stenosis or patient.carotid_stenosis_ge_50
    pad_disease = patient.peripheral_arterial_disease
    if coronary_disease and (pad_disease or carotid_disease):
        extreme_matches.append("冠狀動脈疾病合併周邊動脈疾病或頸動脈狹窄")
    if pad_disease and carotid_disease:
        extreme_matches.append("周邊動脈疾病合併頸動脈狹窄")
    if extreme_matches:
        return "extreme", extreme_matches, notes, missing, review_needed

    very_high_matches: list[str] = []
    if acute_coronary_syndrome:
        very_high_matches.append("急性冠心症病史")
    if patient.coronary_revascularization:
        very_high_matches.append("接受過 PCI / CABG")
    if patient.ischemic_stroke_tia:
        if coronary_disease or pad_disease or carotid_disease:
            very_high_matches.append("缺血性中風／短暫性腦缺血發作合併動脈硬化相關疾病或病史")
        else:
            notes.append("缺血性中風／TIA 需合併 CAD、周邊動脈疾病或頸動脈狹窄，才列為非常高風險。")
    if pad_disease:
        very_high_matches.append("周邊動脈疾病曾接受血管再通術、有肢體缺血相關症狀或截肢")
    if patient.coronary_stenosis_ge_50:
        very_high_matches.append("經影像檢查確認冠狀動脈狹窄 >= 50%")
    if patient.peripheral_stenosis_ge_50:
        very_high_matches.append("經影像檢查確認周邊動脈狹窄 >= 50%")
    if patient.carotid_stenosis_ge_50:
        very_high_matches.append("經影像檢查確認頸動脈狹窄 >= 50%")
    if patient.arterial_stenosis_ge_50 and not very_high_matches:
        very_high_matches.append("經影像檢查確認動脈狹窄 >= 50%")
    if very_high_matches:
        return "very_high", very_high_matches, notes, missing, review_needed

    ckd_ok, ckd_matches, ckd_notes, ckd_missing = _has_persistent_ckd_by_proposal(patient)
    ckd_evidence_supplied = any(
        [
            patient.ckd_persistent_3m,
            patient.egfr_value_1,
            patient.egfr_value_2,
            patient.uacr_value_1,
            patient.uacr_value_2,
            patient.creatinine_latest,
            patient.creatinine_past,
        ]
    )
    if ckd_ok or ckd_evidence_supplied:
        notes.extend(ckd_notes)
        missing.extend(ckd_missing)
        if ckd_missing:
            review_needed = True

    high_matches: list[str] = []
    if patient.diabetes:
        high_matches.append("糖尿病")
    if ckd_ok:
        high_matches.append("進入透析前的慢性腎臟病")
    if patient.ldl_c is not None and patient.ldl_c >= 190:
        high_matches.append("LDL-C >= 190")
    if patient.cac_score is not None and patient.cac_score >= 400:
        high_matches.append("冠狀動脈鈣化分數 (CAC) >= 400")
    if high_matches:
        return "high", high_matches, notes, sorted(set(missing)), review_needed

    risk_factor_count, risk_matches, risk_notes, risk_missing = _new_risk_factor_count(patient)
    notes.extend(risk_notes)
    missing.extend(risk_missing)
    if risk_missing:
        review_needed = True

    if risk_factor_count >= 2:
        return "moderate", risk_matches, notes, sorted(set(missing)), review_needed
    if risk_factor_count == 1:
        return "low", risk_matches, notes, sorted(set(missing)), review_needed
    return "minimal", [], notes, sorted(set(missing)), review_needed


def evaluate_new_eligibility(patient: PatientData) -> RuleOutcome:
    matched: list[str] = []
    missing: list[str] = []
    notes: list[str] = []

    if patient.ldl_c is None:
        missing.append("LDL-C")
        return RuleOutcome(
            title="新制健保給付判定",
            status="needs_review",
            summary="缺少 LDL-C，無法完整進行新制判讀。",
            matched_conditions=matched,
            missing_fields=missing,
            follow_up_notes=notes,
            risk_category="",
        )

    category_key, category_matches, category_notes, category_missing, category_review = _resolve_new_risk_category(patient)
    matched.extend(category_matches)
    notes.extend(category_notes)
    missing.extend(category_missing)

    category = NEW_RULE_THRESHOLDS[category_key]
    eligible = patient.ldl_c >= category["ldl_threshold"]
    summary = (
        f"{category['label']}，LDL-C {patient.ldl_c:g} mg/dL，達到起始門檻 {category['ldl_threshold']} mg/dL。"
        if eligible
        else f"{category['label']}，LDL-C {patient.ldl_c:g} mg/dL，未達起始門檻 {category['ldl_threshold']} mg/dL。"
    )

    non_hdl = patient.non_hdl_c()
    if category["non_hdl_threshold"] is not None:
        if non_hdl is None:
            missing.extend(["總膽固醇 TC", "HDL-C"])
            notes.append("若要一併參考 non-HDL-C 目標，需補 TC 與 HDL-C。")
            if not _requires_lifestyle_trial(category_key):
                category_review = True
        else:
            notes.append(f"non-HDL-C 為 {non_hdl:g} mg/dL，對應門檻 {category['non_hdl_threshold']} mg/dL。")

    status = "eligible" if eligible else "not_eligible"
    if _requires_lifestyle_trial(category_key):
        notes.append("生活型態改變三到六個月再複檢低密度膽固醇。")
    if category_review:
        status = "needs_review"
        summary = f"{summary} 目前仍有待補資料或需人工複核之處。"

    return RuleOutcome(
        title="新制健保給付判定",
        status=status,
        summary=summary,
        matched_conditions=matched,
        missing_fields=sorted(set(missing)),
        follow_up_notes=notes,
        risk_category=category_key,
        ldl_start_threshold=category["ldl_threshold"],
        non_hdl_target=category["non_hdl_threshold"],
    )


def evaluate_all(patient: PatientData) -> list[RuleOutcome]:
    return [evaluate_new_eligibility(patient)]
