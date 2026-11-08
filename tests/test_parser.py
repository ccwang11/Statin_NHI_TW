import unittest

from statin_nhi.parser import parse_note


class ParserTests(unittest.TestCase):
    def test_fhx_cad_does_not_count_as_patient_ascvd(self) -> None:
        result = parse_note("FHx CAD, father had heart disease. LDL 140")
        self.assertNotIn("ascvd_history", result.extracted_fields)
        self.assertTrue(any("家族史" in flag for flag in result.review_flags))

    def test_plan_pci_possible_cad_does_not_count_as_revascularization(self) -> None:
        result = parse_note("Plan PCI for possible CAD. LDL 150")
        self.assertNotIn("coronary_revascularization", result.extracted_fields)
        self.assertNotIn("ascvd_history", result.extracted_fields)

    def test_completed_pci_and_nstemi_count(self) -> None:
        result = parse_note("s/p PCI for NSTEMI, LDL 120")
        self.assertTrue(result.extracted_fields.get("coronary_revascularization"))
        self.assertTrue(result.extracted_fields.get("acute_coronary_syndrome"))
        self.assertTrue(result.extracted_fields.get("ascvd_history"))

    def test_coronary_stenosis_ge_50_derives_cad(self) -> None:
        result = parse_note("Coronary artery stenosis 70%, LDL 120")
        self.assertTrue(result.extracted_fields.get("coronary_stenosis_ge_50"))
        self.assertTrue(result.extracted_fields.get("arterial_stenosis_ge_50"))
        self.assertTrue(result.extracted_fields.get("ascvd_history"))

    def test_peripheral_stenosis_ge_50_does_not_derive_paod(self) -> None:
        result = parse_note("Peripheral artery stenosis 70%, LDL 120")
        self.assertTrue(result.extracted_fields.get("peripheral_stenosis_ge_50"))
        self.assertTrue(result.extracted_fields.get("arterial_stenosis_ge_50"))
        self.assertNotIn("peripheral_arterial_disease", result.extracted_fields)

    def test_dialysis_is_extracted(self) -> None:
        result = parse_note("CKD on hemodialysis, LDL 120")
        self.assertTrue(result.extracted_fields.get("on_dialysis"))

    def test_plain_cad_and_nstemi_history_both_count_as_cad(self) -> None:
        cad_result = parse_note("Known CAD with LDL 120")
        nstemi_result = parse_note("History of NSTEMI, LDL 120")
        self.assertTrue(cad_result.extracted_fields.get("ascvd_history"))
        self.assertTrue(nstemi_result.extracted_fields.get("acute_coronary_syndrome"))
        self.assertTrue(nstemi_result.extracted_fields.get("ascvd_history"))

    def test_patient_cad_is_not_blocked_by_later_family_history_text(self) -> None:
        result = parse_note("CAD, father also had heart disease")
        self.assertTrue(result.extracted_fields.get("ascvd_history"))

    def test_pad_requires_qualifying_limb_evidence(self) -> None:
        unsupported = parse_note("PAD, LDL 120")
        qualifying = parse_note("PAD with critical limb ischemia, LDL 120")
        self.assertNotIn("peripheral_arterial_disease", unsupported.extracted_fields)
        self.assertTrue(qualifying.extracted_fields.get("peripheral_arterial_disease"))

    def test_egfr_priority_prefers_cr_cys_and_excludes_cys_only(self) -> None:
        result = parse_note("eGFRcys 42, eGFR-EPI 55, eGFRcr-cys 61")
        self.assertEqual(result.extracted_fields.get("egfr"), 61.0)
        self.assertTrue(any("eGFRcys" in note for note in result.notes))
        self.assertTrue(any("eGFRcr-cys" in note for note in result.notes))

    def test_general_glucose_only_requires_review(self) -> None:
        result = parse_note("Glucose 126, TG 250")
        self.assertNotIn("fasting_glucose", result.extracted_fields)
        self.assertTrue(any("glucose" in flag for flag in result.review_flags))

    def test_carotid_plaque_does_not_count_as_carotid_stenosis(self) -> None:
        result = parse_note("Carotid plaque noted on ultrasound.")
        self.assertNotIn("carotid_stenosis", result.extracted_fields)

    def test_creatinine_without_egfr_auto_estimates_egfr_and_date(self) -> None:
        result = parse_note("female 65歲 2026-07-01 Cr 1.4 LDL 120")
        self.assertIn("egfr", result.extracted_fields)
        self.assertEqual(result.extracted_fields.get("egfr_date"), "115/07/01")

    def test_manual_sex_and_age_allow_creatinine_to_estimate_egfr(self) -> None:
        result = parse_note("[2026/07/16] Cr 0.86", fallback_sex="男", fallback_age=72)
        self.assertEqual(result.extracted_fields.get("sex"), "male")
        self.assertEqual(result.extracted_fields.get("age"), 72)
        self.assertEqual(result.extracted_fields.get("egfr_date"), "115/07/16")
        self.assertIsNotNone(result.extracted_fields.get("egfr"))

    def test_dated_creatinine_and_uacr_populate_roc_pairs(self) -> None:
        result = parse_note(
            "72 y/o male. T2DM. HTN. HLD.\n"
            "BH 170 BW 95 WC 110\n"
            "[2026/07/25] TC 250 HDL 35 LDL 165 TG 250 HbA1c 7.1 Cr 1.3\n"
            "[2026/07/25] urine ALB/CRE 40\n"
            "[2026/03/15] Cr 1.5\n"
            "[2026/03/15] urine ALB/CRE 45"
        )
        fields = result.extracted_fields
        self.assertEqual(fields.get("egfr_date_1"), "115/03/15")
        self.assertEqual(fields.get("egfr_date_2"), "115/07/25")
        self.assertLess(fields.get("egfr_value_1", 60), 60)
        self.assertLess(fields.get("egfr_value_2", 60), 60)
        self.assertEqual(fields.get("uacr_date_1"), "115/03/15")
        self.assertEqual(fields.get("uacr_value_1"), 45.0)
        self.assertEqual(fields.get("uacr_date_2"), "115/07/25")
        self.assertEqual(fields.get("uacr_value_2"), 40.0)
        self.assertTrue(fields.get("ckd_persistent_3m"))

    def test_cr_is_blood_creatinine_even_when_uacr_is_on_the_same_summary_line(self) -> None:
        result = parse_note(
            "72 y/o male\n"
            "[2026/07/25] Cr 1.3 urine ALB/CRE 40\n"
            "[2026/03/15] Cr 1.5 urine ALB/CRE 45"
        )
        fields = result.extracted_fields
        self.assertEqual(fields.get("creatinine_latest"), 1.3)
        self.assertEqual(fields.get("creatinine_past"), 1.5)
        self.assertEqual(fields.get("egfr_date_1"), "115/03/15")
        self.assertEqual(fields.get("egfr_date_2"), "115/07/25")
        self.assertTrue(fields.get("ckd_persistent_3m"))

    def test_different_egfr_equations_are_not_mixed_as_chronic_evidence(self) -> None:
        result = parse_note(
            "72 y/o male\n"
            "[2025/01/01] eGFR-EPI 52\n"
            "[2026/06/15] eGFR 48\n"
            "[2026/07/25] Cr 1.3"
        )
        fields = result.extracted_fields
        self.assertNotIn("egfr_date_1", fields)
        self.assertEqual(fields.get("egfr_date_2"), "115/07/25")
        self.assertEqual(fields.get("egfr_date"), "115/07/25")
        self.assertFalse(fields.get("ckd_persistent_3m"))

    def test_historical_table_uses_same_equation_and_compact_roc_dates(self) -> None:
        result = parse_note(
            "名稱/值\tRange\t1150716\t1121106\t1110702\t1110315\n"
            "ALB∕CRE\t~\t290.51\t\t\t\n"
            "ALB/CRE\t~\t\t26.38\tND\t18.66\n\n"
            "名稱/值\tRange\t1150716\t1150716\t1150116\t1141017\t1140728\t1140724\n"
            "CRE\t0.60~1.20\t0.86\t\t0.77\t0.72\t0.61\t1.11\n"
            "eGFR-MDRD\t90~\t68.01\t\t\t\t\t\n"
            "eGFR-EPI\t90~\t69.54\t\t\t\t\t\n"
            "eGFRcr-cys\t~\t\t47\t45\t51\t\n"
            "eGFR\t90~\t\t\t77.26\t83.7\t"
        )
        fields = result.extracted_fields
        self.assertEqual((fields.get("egfr_date_1"), fields.get("egfr_value_1")), ("115/01/16", 45.0))
        self.assertEqual((fields.get("egfr_date_2"), fields.get("egfr_value_2")), ("115/07/16", 47.0))
        self.assertEqual((fields.get("uacr_date_1"), fields.get("uacr_value_1")), ("112/11/06", 26.38))
        self.assertEqual((fields.get("uacr_date_2"), fields.get("uacr_value_2")), ("115/07/16", 290.51))
        self.assertTrue(fields.get("ckd_persistent_3m"))

    def test_dated_order_ignores_urine_creatinine_but_keeps_egfr_and_uacr(self) -> None:
        result = parse_note(
            "115/07/16 CRE：106.95 mg/dL、TP-Urine：103.4 mg/dL、TP∕CRE：966.81 mg/g、ALB：31.07 mg/dL、ALB∕CRE：290.51 mg/g\n"
            "115/07/16 T P：8.5 g/dL、CRE：0.86 mg/dL、eGFR-MDRD：68.01 mL/min、eGFR-EPI：69.54 mL/min"
        )
        fields = result.extracted_fields
        self.assertEqual(fields.get("creatinine_latest"), 0.86)
        self.assertEqual(fields.get("egfr"), 69.54)
        self.assertEqual(fields.get("egfr_date"), "115/07/16")
        self.assertEqual(fields.get("uacr"), 290.51)

    def test_single_report_table_inherits_dates_and_ignores_urine_creatinine(self) -> None:
        result = parse_note(
            "報告日期\t檢驗項目\t檢驗報告\t單位\n"
            "1150716\tCRE\t0.86\tmg/dL\n"
            "\teGFR-MDRD\t68.01\tmL/min\n"
            "\teGFR-EPI\t69.54\tmL/min\n"
            "1150716\tCRE\t106.95\tmg/dL\n"
            "\tTP-Urine\t103.4\tmg/dL\n"
            "\tTP∕CRE\t966.81\tmg/g\n"
            "\tALB∕CRE\t290.51\tmg/g"
        )
        fields = result.extracted_fields
        self.assertEqual(fields.get("creatinine_latest"), 0.86)
        self.assertEqual(fields.get("egfr"), 69.54)
        self.assertEqual(fields.get("uacr"), 290.51)

    def test_metabolic_measurement_aliases_are_extracted(self) -> None:
        result = parse_note("WC: 91, FBG: 102, TG: 180, ALB/CRE: 35")
        self.assertEqual(result.extracted_fields.get("waist_cm"), 91.0)
        self.assertEqual(result.extracted_fields.get("fasting_glucose"), 102.0)
        self.assertEqual(result.extracted_fields.get("triglycerides"), 180.0)
        self.assertEqual(result.extracted_fields.get("uacr"), 35.0)

    def test_multivessel_and_pobas_are_recognized(self) -> None:
        result = parse_note("Known 3VD, s/p POBAS")
        self.assertTrue(result.extracted_fields.get("multivessel_coronary_disease"))
        self.assertTrue(result.extracted_fields.get("coronary_revascularization"))
        self.assertTrue(result.extracted_fields.get("ascvd_history"))

    def test_mi_counts_as_acute_coronary_syndrome(self) -> None:
        result = parse_note("History of MI")
        self.assertTrue(result.extracted_fields.get("acute_coronary_syndrome"))

    def test_hemorrhagic_stroke_is_not_counted_as_ischemic_stroke(self) -> None:
        result = parse_note("History of hemorrhagic stroke")
        self.assertNotIn("ischemic_stroke_tia", result.extracted_fields)

    def test_lipid_lowering_medication_is_extracted(self) -> None:
        result = parse_note("Current medications: Crestor 10 mg daily")
        self.assertTrue(result.extracted_fields.get("on_lipid_lowering_medication"))
        self.assertTrue(result.extracted_fields.get("on_statin_medication"))

    def test_english_age_formats_are_extracted(self) -> None:
        for text in ("72 y/o male", "72 yo male", "72 years old male", "72-year-old male"):
            with self.subTest(text=text):
                self.assertEqual(parse_note(text).extracted_fields.get("age"), 72.0)

    def test_ezetimibe_is_not_classified_as_statin(self) -> None:
        result = parse_note("Current medications: Ezetrol 10 mg daily")
        self.assertTrue(result.extracted_fields.get("on_lipid_lowering_medication"))
        self.assertNotIn("on_statin_medication", result.extracted_fields)

    def test_combination_and_pure_tg_medications_are_distinguished(self) -> None:
        combination = parse_note("Pravafen and Caduet are continued")
        pure_tg = parse_note("Fenolip-U 160 mg daily")
        self.assertTrue(combination.extracted_fields.get("on_lipid_lowering_medication"))
        self.assertTrue(combination.extracted_fields.get("on_tg_medication"))
        self.assertTrue(pure_tg.extracted_fields.get("on_tg_medication"))
        self.assertNotIn("on_lipid_lowering_medication", pure_tg.extracted_fields)


if __name__ == "__main__":
    unittest.main()
