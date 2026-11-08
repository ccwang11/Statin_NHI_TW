from datetime import date
from unittest.mock import patch
import tempfile
from pathlib import Path
import unittest

from statin_nhi.medications import (
    MedicationCatalog,
    default_catalog_path,
    load_hospital_medication_codes,
    medication_output_lines,
    normalize_medication_code,
    save_hospital_medication_codes,
)


class MedicationCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = MedicationCatalog.from_csv(default_catalog_path())

    def test_catalog_uses_code_as_the_only_lookup_key(self) -> None:
        medication = self.catalog.lookup(" bc28787100 ")
        self.assertIsNotNone(medication)
        self.assertEqual(medication.code, "BC28787100")
        self.assertEqual(medication.ingredient, "Atorvastatin")
        self.assertIsNone(self.catalog.lookup("Tulip 40mg"))
        self.assertEqual(normalize_medication_code("BC 28787100"), "BC28787100")

    def test_only_master_codes_are_saved_and_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Statin_NHI_available.json"
            saved = save_hospital_medication_codes(
                path,
                ["BC24131100", "AC37685100", "BC28787100", "BC24131100"],
                self.catalog,
            )
            loaded, error = load_hospital_medication_codes(path, self.catalog)
        self.assertEqual(saved, ["BC24131100", "BC28787100"])
        self.assertEqual(loaded, saved)
        self.assertIsNone(error)

    def test_output_groups_only_selected_hospital_medications(self) -> None:
        medications = self.catalog.selected(["BC28787100", "BC24058100", "BC27283100"])
        self.assertEqual(
            medication_output_lines(medications, as_of=date(2026, 9, 1)),
            [
                "新制可用高強度 Statin：Tulip SDZ Film Coated Tablet 40mg (Atorvastatin)",
                "新制可用輔助藥物：EZETROL Tablets 10mg (Ezetimibe)",
                "新制可用複方藥物：ATOZET F.C. Tablets 10/20mg (Ezetimibe/Atorvastatin)",
            ],
        )

    def test_effective_date_boundaries(self) -> None:
        codes = list(self.catalog._by_code)
        medications = self.catalog.selected(codes)
        self.assertEqual(len(medications), 63)
        for day, count in [(date(2026, 8, 31), 0), (date(2026, 9, 1), 57),
                           (date(2026, 11, 30), 57), (date(2026, 12, 1), 63)]:
            with self.subTest(day=day):
                self.assertEqual(sum(m.is_effective(day) for m in medications), count)
        future = self.catalog.selected(["AC57930100", "BC25350100", "BC27002100",
                                        "AC62140100", "AC62139100", "BC28884100"])
        self.assertEqual(medication_output_lines(future, date(2026, 11, 30)), [])
        self.assertEqual(len(medication_output_lines(future, date(2026, 12, 1))), 2)

    def test_future_settings_survive_and_activate_without_reloading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_hospital_medication_codes(path, ["BC25350100", "BC24131100"], self.catalog)
            loaded, error = load_hospital_medication_codes(path, self.catalog)
        self.assertIsNone(error)
        self.assertEqual(loaded, ["BC25350100", "BC24131100"])
        medications = self.catalog.selected(loaded)
        with patch("statin_nhi.medications.taiwan_today", return_value=date(2026, 11, 30)):
            self.assertNotIn("Livalo", "\n".join(medication_output_lines(medications)))
        with patch("statin_nhi.medications.taiwan_today", return_value=date(2026, 12, 1)):
            self.assertIn("Livalo", "\n".join(medication_output_lines(medications)))

    def test_invalid_or_missing_effective_date_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.csv"
            for value in ["2026-02-30", "20261201", ""]:
                with self.subTest(value=value):
                    path.write_text("code,display_name,ingredient,category,effective_date\n"
                                    f"BC25350100,Livalo,Pitavastatin,中強度 Statin,{value}\n", encoding="utf-8")
                    with self.assertRaises(ValueError):
                        MedicationCatalog.from_csv(path)

    def test_update_reminder_any_code_and_persistent_dismissal(self) -> None:
        from statin_nhi.medications import (
            NEW_MEDICATION_CODES, should_show_medication_update, dismiss_medication_update,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Statin_NHI_available.json"
            self.assertTrue(should_show_medication_update([], path))
            self.assertTrue(should_show_medication_update(["BC24131100"], path))
            for code in NEW_MEDICATION_CODES:
                self.assertFalse(should_show_medication_update([code], path))
            path.write_text("invalid json")
            self.assertTrue(should_show_medication_update([], path))
            with self.assertRaises(OSError):
                dismiss_medication_update(path)
            path.write_text('{"medication_codes": [], "dismissed_updates": {"other_update": true}}')
            dismiss_medication_update(path)
            self.assertFalse(should_show_medication_update([], path))
            path.write_text('{"medication_codes": [], "dismissed_updates": {"other_update": true}}')
            self.assertTrue(should_show_medication_update([], path))
            dismiss_medication_update(path)
            import json
            self.assertTrue(json.loads(path.read_text())["dismissed_updates"]["other_update"])

    def test_medication_and_reminder_saves_preserve_each_other(self) -> None:
        import json
        from statin_nhi.medications import dismiss_medication_update, should_show_medication_update
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Statin_NHI_available.json"
            save_hospital_medication_codes(path, ["BC24131100"], self.catalog)
            dismiss_medication_update(path)
            self.assertEqual(load_hospital_medication_codes(path, self.catalog)[0], ["BC24131100"])
            save_hospital_medication_codes(path, ["BC24058100"], self.catalog)
            self.assertFalse(should_show_medication_update(["BC24058100"], path))
            self.assertEqual(json.loads(path.read_text())["medication_codes"], ["BC24058100"])

    def test_legacy_reminders_migrate_without_changing_hospital_codes(self) -> None:
        import json
        from statin_nhi.medications import REMINDER_FILENAME, should_show_medication_update
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Statin_NHI_available.json"
            save_hospital_medication_codes(path, ["BC24131100"], self.catalog)
            legacy = path.with_name(REMINDER_FILENAME)
            legacy.write_text('{"1150672925": true}')
            self.assertFalse(should_show_medication_update([], path))
            payload = json.loads(path.read_text())
            self.assertEqual(payload["medication_codes"], ["BC24131100"])
            self.assertTrue(payload["dismissed_updates"]["1150672925"])
            legacy.unlink()
            self.assertFalse(should_show_medication_update([], path))

    def test_corrupt_shared_settings_are_not_overwritten(self) -> None:
        from statin_nhi.medications import dismiss_medication_update
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("invalid json")
            with self.assertRaises(OSError):
                save_hospital_medication_codes(path, ["BC24131100"], self.catalog)
            with self.assertRaises(OSError):
                dismiss_medication_update(path)
            self.assertEqual(path.read_text(), "invalid json")

    def test_invalid_settings_file_falls_back_to_no_medications(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Statin_NHI_available.json"
            path.write_text("not json", encoding="utf-8")
            loaded, error = load_hospital_medication_codes(path, self.catalog)
        self.assertEqual(loaded, [])
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
