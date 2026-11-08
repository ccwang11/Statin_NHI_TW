import unittest

from statin_nhi.models import PatientData
from statin_nhi.rules import evaluate_new_eligibility
from statin_nhi.ui import App


class OutputTests(unittest.TestCase):
    def test_eligible_output_includes_targets_medications_and_follow_up(self) -> None:
        patient = PatientData(
            ldl_c=80,
            total_cholesterol=160,
            hdl_c=40,
            peripheral_arterial_disease=True,
            carotid_stenosis=True,
        )
        output = "\n".join(App._format_eligibility_output(None, patient, evaluate_new_eligibility(patient)))
        self.assertIn("ASCVD 風險等級：極高風險（周邊動脈疾病合併頸動脈狹窄）", output)
        self.assertIn("主要/次要血脂目標值：LDL-C < 55 / non-HDL-C < 85", output)
        self.assertNotIn("(未達標)", output)
        self.assertNotIn("資料待確認", output)
        self.assertIn("院內新制可用藥物：尚未設定", output)
        self.assertIn("追蹤時程：", output)
        self.assertNotIn("評估建議：", output)
        self.assertLess(output.index("院內新制可用藥物：尚未設定"), output.index("追蹤時程："))

    def test_initial_treatment_lists_secondary_target_without_tc_or_hdl(self) -> None:
        patient = PatientData(ldl_c=80, peripheral_arterial_disease=True, carotid_stenosis=True)
        output = "\n".join(App._format_eligibility_output(None, patient, evaluate_new_eligibility(patient)))
        self.assertIn("主要/次要血脂目標值：LDL-C < 55 / non-HDL-C < 85", output)
        self.assertNotIn("缺 TC", output)
        self.assertNotIn("缺 HDL", output)

    def test_below_threshold_output_omits_medications_and_follow_up(self) -> None:
        patient = PatientData(sex="male", age=40, ldl_c=100, hypertension=True)
        output = "\n".join(App._format_eligibility_output(None, patient, evaluate_new_eligibility(patient)))
        self.assertIn("LDL-C 低於起始藥物治療血脂值", output)
        self.assertNotIn("院內新制可用藥物：尚未設定", output)
        self.assertNotIn("追蹤時程：", output)
        self.assertNotIn("PCSK9", output)

    def test_treated_patient_omits_initial_treatment_lines_but_keeps_targets(self) -> None:
        patient = PatientData(
            sex="male",
            age=40,
            ldl_c=90,
            total_cholesterol=145,
            hdl_c=45,
            hypertension=True,
            on_lipid_lowering_medication=True,
            on_statin_medication=True,
        )
        output = "\n".join(App._format_eligibility_output(None, patient, evaluate_new_eligibility(patient)))
        self.assertNotIn("起始藥物治療血脂值", output)
        self.assertNotIn("非藥物治療：", output)
        self.assertIn("主要/次要血脂目標值：LDL-C < 130 (已達標)", output)
        self.assertIn("追蹤時程：", output)
        self.assertIn("院內新制可用藥物：尚未設定", output)
        self.assertNotIn("PCSK9", output)

    def test_statin_user_not_at_target_shows_goal_status_and_pcsk9_note(self) -> None:
        patient = PatientData(
            ldl_c=80,
            total_cholesterol=160,
            hdl_c=40,
            peripheral_arterial_disease=True,
            carotid_stenosis=True,
            on_lipid_lowering_medication=True,
            on_statin_medication=True,
        )
        output = "\n".join(App._format_eligibility_output(None, patient, evaluate_new_eligibility(patient)))
        self.assertIn("LDL-C < 55 (未達標)", output)
        self.assertIn("non-HDL-C < 85 (未達標)", output)
        self.assertIn("PCSK9", output)
        self.assertLess(output.index("PCSK9"), output.index("追蹤時程："))

    def test_statin_user_without_non_hdl_inputs_shows_missing_data(self) -> None:
        base = {
            "ldl_c": 80,
            "peripheral_arterial_disease": True,
            "carotid_stenosis": True,
            "on_lipid_lowering_medication": True,
            "on_statin_medication": True,
        }
        cases = [
            ({"hdl_c": 40}, "non-HDL-C < 85 (缺 TC)"),
            ({"total_cholesterol": 160}, "non-HDL-C < 85 (缺 HDL)"),
            ({}, "non-HDL-C < 85 (缺 TC, HDL)"),
        ]
        for values, expected in cases:
            with self.subTest(expected=expected):
                patient = PatientData(**base, **values)
                output = "\n".join(App._format_eligibility_output(None, patient, evaluate_new_eligibility(patient)))
                self.assertIn(expected, output)


if __name__ == "__main__":
    unittest.main()
