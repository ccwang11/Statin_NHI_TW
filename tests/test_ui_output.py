import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from statin_nhi.models import PatientData
from statin_nhi.rules import evaluate_new_eligibility
from statin_nhi.ui import App, NUMERIC_LABELS, OUTPUT_DIVIDER, parse_nonnegative_number


class OutputTests(unittest.TestCase):
    def test_incomplete_ckd_evidence_keeps_review_warning_in_copied_summary(self) -> None:
        patient = PatientData(ldl_c=170, sex="male", age=50,
                              egfr_date_1="2026-01-01", egfr_value_1=40)
        outcome = evaluate_new_eligibility(patient)
        self.assertEqual(outcome.status, "needs_review")
        output = "\n".join(App._format_eligibility_output(None, patient, outcome))
        app = SimpleNamespace(result_text=Mock(), clipboard_clear=Mock(),
                              clipboard_append=Mock(), update_idletasks=Mock())
        app.result_text.get.return_value = output
        App.copy_result_summary(app)
        summary = app.clipboard_append.call_args.args[0]
        self.assertIn("暫定分級，需人工複核", summary)
        self.assertIn("eGFR 第2次數值", summary)
        for note in outcome.follow_up_notes:
            self.assertIn(note, summary)
        self.assertNotIn(OUTPUT_DIVIDER, summary)
        self.assertNotIn("院內新制可用藥物", summary)

    def test_below_threshold_still_displays_review_reasons(self) -> None:
        patient = PatientData(ldl_c=80, sex="male", age=50,
                              egfr_date_1="2026-01-01", egfr_value_1=40)
        outcome = evaluate_new_eligibility(patient)
        output = "\n".join(App._format_eligibility_output(None, patient, outcome))
        self.assertIn("需人工複核", output)
        self.assertIn("待補資料：", output)
        self.assertNotIn("院內新制可用藥物", output)

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
        self.assertIn("需人工複核", output)
        self.assertIn("總膽固醇 TC", output)

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


class NumericInputTests(unittest.TestCase):
    def form(self, **values):
        fields = {name: Mock(get=Mock(return_value="")) for name in NUMERIC_LABELS}
        fields["bp_text"] = Mock(get=Mock(return_value=""))
        for name, value in values.items():
            fields[name].get.return_value = value
        return SimpleNamespace(field_vars=fields)

    def test_invalid_measurements_are_rejected_for_each_numeric_field(self):
        for name in NUMERIC_LABELS:
            for raw in ("-10", "nan", "inf", "-inf", "1e999", "abc"):
                with self.subTest(field=name, raw=raw):
                    with self.assertRaises(ValueError):
                        App._validate_numeric_inputs(self.form(**{name: raw}))

    def test_blank_zero_and_decimal_values_remain_supported(self):
        self.assertIsNone(parse_nonnegative_number(" "))
        self.assertEqual(parse_nonnegative_number("0"), 0)
        self.assertEqual(parse_nonnegative_number(" 123.5 "), 123.5)
        App._validate_numeric_inputs(self.form(ldl_c="123.5", uacr_value_1="0", bp_text="120/80"))

    def test_malformed_or_nonfinite_blood_pressure_is_rejected(self):
        for raw in ("120", "120/", "/80", "nan/80", "120/inf", "-1/80", "120/80/90"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                App._validate_numeric_inputs(self.form(bp_text=raw))

    def test_invalid_input_clears_stale_result_and_stops_rule_evaluation(self):
        app = self.form(ldl_c="inf")
        app.build_patient_data = lambda: App.build_patient_data(app)
        app._validate_numeric_inputs = lambda: App._validate_numeric_inputs(app)
        app.result_text = Mock()
        with patch("statin_nhi.ui.messagebox.showwarning") as warning, patch("statin_nhi.ui.evaluate_all") as evaluate:
            App.evaluate_patient(app)
        evaluate.assert_not_called()
        warning.assert_called_once()
        app.result_text.delete.assert_called_once_with("1.0", "end")
        self.assertIn("尚未判讀", app.result_text.insert.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
