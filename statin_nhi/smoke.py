"""GUI smoke checks shared by source and the frozen Windows application."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import patch


def run_smoke(report_path: Path) -> None:
    import customtkinter as ctk
    from PIL import ImageGrab
    from . import __version__
    from .ui import App
    from .medications import MedicationCatalog, default_catalog_path, save_hospital_medication_codes

    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    root = None
    report = {"version": __version__, "ok": False}
    try:
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "Statin_NHI_available.json"
            catalog = MedicationCatalog.from_csv(default_catalog_path())
            save_hospital_medication_codes(settings, ["BC24131100", "BC25350100", "AC62140100"], catalog)
            with patch("statin_nhi.ui.default_settings_path", return_value=settings):
                root = ctk.CTk()
                app = App(root, startup_reminder=False)
            root.update()
            app.open_hospital_medication_matcher()
            root.update()

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            dialogs = [w for w in descendants(root) if isinstance(w, ctk.CTkToplevel)]
            assert len(dialogs) == 1, "Medication dialog did not open"
            dialog = dialogs[0]
            labels = [w for w in descendants(dialog) if isinstance(w, ctk.CTkLabel)]
            texts = []
            for label in labels:
                variable = label.cget("textvariable")
                texts.append(str(root.getvar(str(variable))) if variable else str(label.cget("text")))
                if label.winfo_ismapped():
                    assert label.winfo_rootx() + label.winfo_width() <= dialog.winfo_rootx() + dialog.winfo_width() + 2, "Label extends beyond dialog"
            assert "給付生效日期" in texts
            assert "2026/09/01" in texts
            assert any(t.startswith("2026/12/01") for t in texts)
            ImageGrab.grab().save(report_path.with_name(report_path.stem + "-medications.png"))
            dialog.grab_release()
            dialog.destroy()
            # The reminder must not open when any one new code has been configured.
            app.show_medication_update()
            root.update()
            assert not any(isinstance(w, ctk.CTkToplevel) for w in descendants(root))
            app.hospital_medication_codes = []
            app.show_medication_update()
            root.update()
            dialogs = [w for w in descendants(root) if isinstance(w, ctk.CTkToplevel)]
            assert len(dialogs) == 1, "Update reminder did not open"
            dialog = dialogs[0]
            listing = next(w for w in descendants(dialog) if isinstance(w, ctk.CTkTextbox))
            for code in ("AC57930100", "BC25350100", "BC27002100", "AC62140100", "AC62139100", "BC28884100"):
                assert code in listing.get("1.0", "end")
            ImageGrab.grab().save(report_path.with_name(report_path.stem + "-reminder.png"))
            # Verify the actual checkbox/button callbacks persist dismissal.
            checkbox = next(w for w in descendants(dialog) if isinstance(w, ctk.CTkCheckBox))
            checkbox.select()
            button = next(w for w in descendants(dialog) if isinstance(w, ctk.CTkButton) and w.cget("text") == "稍後設定")
            button.invoke()
            app.show_medication_update()
            root.update()
            assert not any(isinstance(w, ctk.CTkToplevel) for w in descendants(root))
            from .medications import REIMBURSEMENT_UPDATE_ID, REMINDER_FILENAME
            saved = json.loads(settings.read_text(encoding="utf-8"))
            assert saved["dismissed_updates"][REIMBURSEMENT_UPDATE_ID] is True
            assert saved["medication_codes"] == ["BC24131100", "BC25350100", "AC62140100"]
            assert not settings.with_name(REMINDER_FILENAME).exists()
            # Synthetic evidence exercises the visible review and clipboard flow.
            app.clear_all()
            for name, value in {"sex": "male", "age": "50", "ldl_c": "170",
                                "egfr_date_1": "2026-01-01", "egfr_value_1": "40"}.items():
                app.field_vars[name].set(value)
            app.evaluate_patient()
            root.update()
            app.copy_result_summary()
            summary = root.clipboard_get()
            assert "暫定分級，需人工複核" in summary
            assert "eGFR 第2次數值" in summary
            assert "院內新制可用藥物" not in summary
            app.field_vars["ldl_c"].set("inf")
            with patch("statin_nhi.ui.messagebox.showwarning") as warning:
                app.evaluate_patient()
                warning.assert_called_once()
            assert "尚未判讀" in app.result_text.get("1.0", "end")
            assert "ASCVD 風險等級" not in app.result_text.get("1.0", "end")

            # A complete synthetic example for documentation; no hospital defaults.
            app.clear_all()
            app.note_text.insert("1.0", "人工範例，非真實病歷：50 歲男性，周邊動脈疾病合併頸動脈狹窄。\nLDL-C 80、TC 160、HDL-C 40 mg/dL。")
            for name, value in {"sex": "male", "age": "50", "ldl_c": "80",
                                "total_cholesterol": "160", "hdl_c": "40",
                                "peripheral_arterial_disease": True, "carotid_stenosis": True}.items():
                app.field_vars[name].set(value)
            app.evaluate_patient()
            root.update()
            assert "極高風險" in app.result_text.get("1.0", "end")
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                report_path.with_name(report_path.stem + "-example.png"))
            report.update(ok=True, checks=["catalog bundled", "date columns", "dialog bounds", "any-code suppression", "six-code reminder", "persistent dismissal", "review summary clipboard", "invalid input stops evaluation", "synthetic example"])
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        if root is not None:
            root.destroy()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import sys
    run_smoke(Path(sys.argv[1]))
