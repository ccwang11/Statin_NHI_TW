import unittest

from statin_nhi.models import PatientData
from statin_nhi.rules import evaluate_all, evaluate_new_eligibility


class RulesTests(unittest.TestCase):
    def test_cad_only_is_not_very_high_risk(self) -> None:
        patient = PatientData(
            sex="male",
            age=40,
            ldl_c=170,
            ascvd_history=True,
            waist_cm=80,
            systolic_bp=120,
            diastolic_bp=75,
            fasting_glucose=90,
            triglycerides=100,
            hdl_c=45,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("新制零危險因子", outcome.summary)

    def test_paod_plus_carotid_is_extreme_risk(self) -> None:
        patient = PatientData(ldl_c=80, peripheral_arterial_disease=True, carotid_stenosis=True)
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("新制極高風險", outcome.summary)
        self.assertIn("周邊動脈疾病合併頸動脈狹窄", outcome.matched_conditions)

    def test_coronary_stenosis_and_paod_is_extreme_risk(self) -> None:
        patient = PatientData(ldl_c=80, coronary_stenosis_ge_50=True, peripheral_arterial_disease=True)
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("新制極高風險", outcome.summary)
        self.assertIn("冠狀動脈疾病合併周邊動脈疾病或頸動脈狹窄", outcome.matched_conditions)

    def test_stroke_without_other_vascular_disease_is_not_very_high_risk(self) -> None:
        patient = PatientData(
            sex="male",
            age=40,
            ldl_c=170,
            ischemic_stroke_tia=True,
            waist_cm=80,
            systolic_bp=120,
            diastolic_bp=75,
            fasting_glucose=90,
            triglycerides=100,
            hdl_c=45,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertNotIn("新制非常高風險", outcome.summary)
        self.assertTrue(any("缺血性中風" in note for note in outcome.follow_up_notes))

    def test_stroke_with_carotid_stenosis_is_very_high_risk(self) -> None:
        patient = PatientData(ldl_c=80, ischemic_stroke_tia=True, carotid_stenosis=True)
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("新制非常高風險", outcome.summary)

    def test_new_ckd_from_creatinine_path_can_be_eligible(self) -> None:
        patient = PatientData(
            sex="female",
            age=65,
            ldl_c=120,
            creatinine_latest=1.4,
            creatinine_past=1.2,
            creatinine_month_gap=4,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertEqual(outcome.status, "needs_review")
        self.assertIn("進入透析前的慢性腎臟病", outcome.matched_conditions)
        self.assertIn("總膽固醇 TC", outcome.missing_fields)
        self.assertIn("HDL-C", outcome.missing_fields)

    def test_new_ckd_large_creatinine_delta_does_not_auto_count(self) -> None:
        patient = PatientData(
            sex="male",
            age=70,
            ldl_c=120,
            creatinine_latest=2.0,
            creatinine_past=1.0,
            creatinine_month_gap=4,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertNotIn("符合新制高風險條件", outcome.matched_conditions)
        self.assertTrue(any("AKI" in note for note in outcome.follow_up_notes))

    def test_evaluate_all_returns_one_new_rule_outcome(self) -> None:
        patient = PatientData(ldl_c=150)
        outcomes = evaluate_all(patient)
        self.assertEqual(len(outcomes), 1)

    def test_carotid_stenosis_with_cad_is_extreme_without_percent_field(self) -> None:
        patient = PatientData(ldl_c=90, ascvd_history=True, carotid_stenosis=True)
        outcome = evaluate_new_eligibility(patient)
        self.assertEqual(outcome.status, "needs_review")
        self.assertIn("冠狀動脈疾病合併周邊動脈疾病或頸動脈狹窄", outcome.matched_conditions)
        self.assertNotIn("頸動脈狹窄百分比", outcome.missing_fields)

    def test_imaging_stenosis_ge_50_is_very_high_risk(self) -> None:
        patient = PatientData(ldl_c=75, arterial_stenosis_ge_50=True)
        outcome = evaluate_new_eligibility(patient)
        self.assertEqual(outcome.status, "needs_review")
        self.assertIn("經影像檢查確認動脈狹窄 >= 50%", outcome.matched_conditions)

    def test_dialysis_does_not_count_as_predialysis_ckd(self) -> None:
        patient = PatientData(ldl_c=120, ckd_persistent_3m=True, on_dialysis=True)
        outcome = evaluate_new_eligibility(patient)
        self.assertNotIn("符合新制高風險條件", outcome.matched_conditions)
        self.assertTrue(any("透析" in note for note in outcome.follow_up_notes))

    def test_hypertension_is_a_standalone_risk_factor(self) -> None:
        patient = PatientData(
            sex="male",
            age=40,
            ldl_c=140,
            hypertension=True,
            waist_cm=80,
            fasting_glucose=90,
            triglycerides=100,
            hdl_c=45,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("新制低風險", outcome.summary)
        self.assertIn("高血壓", outcome.matched_conditions)

    def test_diabetes_directly_satisfies_metabolic_glucose_component(self) -> None:
        patient = PatientData(
            sex="female",
            age=60,
            ldl_c=120,
            diabetes=True,
            waist_cm=82,
            triglycerides=180,
            hdl_c=45,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("糖尿病", outcome.matched_conditions)

    def test_metabolic_syndrome_uses_single_values(self) -> None:
        patient = PatientData(
            sex="male",
            age=40,
            ldl_c=120,
            waist_cm=92,
            systolic_bp=135,
            fasting_glucose=105,
            triglycerides=120,
            hdl_c=45,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertIn("代謝症候群", outcome.matched_conditions)

    def test_moderate_or_lower_shows_lifestyle_follow_up_without_review_status(self) -> None:
        patient = PatientData(
            sex="male",
            age=40,
            ldl_c=170,
            waist_cm=80,
            systolic_bp=120,
            diastolic_bp=75,
            fasting_glucose=90,
            triglycerides=100,
            hdl_c=45,
        )
        outcome = evaluate_new_eligibility(patient)
        self.assertEqual(outcome.status, "eligible")
        self.assertIn("生活型態改變三到六個月再複檢低密度膽固醇。", outcome.follow_up_notes)


if __name__ == "__main__":
    unittest.main()
