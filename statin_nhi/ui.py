from __future__ import annotations

from collections.abc import Callable
import math
import sys
import tkinter as tk
from tkinter import messagebox
import webbrowser

import customtkinter as ctk

from . import __version__
from .fh import FHScreeningData, evaluate_fh_screening
from .medications import (
    MedicationCatalog,
    NEW_MEDICATION_CODES,
    dismiss_medication_update,
    should_show_medication_update,
    bundled_resource_path,
    default_catalog_path,
    default_settings_path,
    load_hospital_medication_codes,
    medication_output_lines,
    normalize_medication_code,
    save_hospital_medication_codes,
)
from .models import PatientData, RuleOutcome, format_roc_date, parse_clinical_date
from .parser import parse_note
from .rules import _estimate_egfr_epi_2021, evaluate_all


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


COMMON_FIELDS = [
    ("sex", "性別", "choice", ["", "male", "female"]),
    ("age", "年齡", "number", None),
    ("ldl_c", "LDL-C", "number", None),
    ("total_cholesterol", "TC", "number", None),
]

PAIR_FIELD_NAMES = [
    "egfr_date_1",
    "egfr_value_1",
    "egfr_date_2",
    "egfr_value_2",
    "uacr_date_1",
    "uacr_value_1",
    "uacr_date_2",
    "uacr_value_2",
    "creatinine_latest",
    "creatinine_latest_date",
    "creatinine_past",
    "creatinine_past_date",
    "creatinine_month_gap",
]

RISK_LABELS = {
    "extreme": "極高風險",
    "very_high": "非常高風險",
    "high": "高風險",
    "moderate": "中風險",
    "low": "低風險",
    "minimal": "零風險因子",
}

OUTPUT_DIVIDER = "-" * 30
BUTTON_HEIGHT = 34

NUMERIC_LABELS = {
    **{name: label for name, label, kind, _ in COMMON_FIELDS if kind == "number"},
    "cac_score": "CAC", "waist_cm": "腹圍", "fasting_glucose": "空腹血糖",
    "triglycerides": "空腹 TG", "hdl_c": "HDL-C",
    "egfr_value_1": "eGFR 第1次數值", "egfr_value_2": "eGFR 第2次數值",
    "uacr_value_1": "UACR 第1次數值", "uacr_value_2": "UACR 第2次數值",
    "creatinine_latest": "最近 creatinine", "creatinine_past": "較早 creatinine",
    "creatinine_month_gap": "creatinine 間隔月數",
}


def parse_nonnegative_number(raw: str) -> float | None:
    if not raw.strip():
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValueError("數值必須為有限且不小於零的數字")
    return value


def action_button_font() -> ctk.CTkFont:
    return ctk.CTkFont(family="Microsoft JhengHei UI", size=16, weight="bold")


class SectionFrame(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        title: str,
        note: str = "",
        on_toggle: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, corner_radius=14, fg_color="#F8FAFC", border_width=1, border_color="#D7E1EC")
        # Each section has one responsive content column.  Nested row frames own
        # their column sizing, so the form never becomes wider than the sidebar.
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(self, width=34, height=4, corner_radius=6, fg_color="#1D6FD6").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0)
        )
        self._title = title
        self._expanded = True
        self._content_children = []
        self._toggle_button: ctk.CTkButton | None = None
        title_font = ctk.CTkFont(family="Microsoft JhengHei UI", size=17, weight="bold")
        if on_toggle is None:
            ctk.CTkLabel(self, text=title, font=title_font, text_color="#16324F").grid(
                row=1, column=0, sticky="w", padx=12, pady=(6, 2)
            )
        else:
            self._toggle_button = ctk.CTkButton(
                self,
                text="",
                command=on_toggle,
                anchor="w",
                height=BUTTON_HEIGHT,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#E8F1F9",
                text_color="#16324F",
                font=action_button_font(),
            )
            self._toggle_button.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 2))
            self._update_toggle_text()

        # The compact clinic layout keeps explanatory text out of the form.
        self.first_row = 2

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        if expanded:
            for child in self._content_children:
                child.grid()
        else:
            self._content_children = []
            for child in self.winfo_children():
                grid_info = child.grid_info()
                if not grid_info or int(grid_info.get("row", -1)) < self.first_row:
                    continue
                self._content_children.append(child)
                child.grid_remove()
        self._update_toggle_text()

    def _update_toggle_text(self) -> None:
        if self._toggle_button is not None:
            indicator = "[-]" if self._expanded else "[+]"
            self._toggle_button.configure(text=f"{indicator} {self._title}")


class App(ctk.CTkFrame):
    def __init__(self, master: ctk.CTk, *, startup_reminder: bool = True) -> None:
        super().__init__(master, fg_color="#EEF3F8")
        self.master = master
        self.field_vars: dict[str, tk.Variable] = {}
        self.field_widgets: dict[str, object] = {}
        self.section_frames: dict[str, SectionFrame] = {}
        self._auto_derived_fields: set[str] = set()
        self._egfr_derived_from_creatinine = False
        self._updating_derived_egfr = False
        self.fh_screening_data: FHScreeningData | None = None
        self.medication_settings_path = default_settings_path()
        self.medication_catalog_error: str | None = None
        try:
            self.medication_catalog = MedicationCatalog.from_csv(default_catalog_path())
        except (OSError, ValueError) as error:
            self.medication_catalog = MedicationCatalog([])
            self.medication_catalog_error = f"新制藥物主檔無法載入：{error}"
        self.hospital_medication_codes, self.medication_settings_error = load_hospital_medication_codes(
            self.medication_settings_path,
            self.medication_catalog,
        )
        self.risk_section_keys = ("extreme_very_high", "high", "moderate_low_minimal")
        self.active_risk_section = "extreme_very_high"
        self.note_text: ctk.CTkTextbox
        self.result_text: ctk.CTkTextbox
        self.risk_hint_var = tk.StringVar(value="依風險優先順序填寫")
        self.pack(fill="both", expand=True)
        self._initialize_hidden_fields()
        self._build_ui()
        self._bind_dynamic_updates()
        self.refresh_dynamic_ui()
        if startup_reminder:
            self.after(500, self.show_medication_update)

    def _initialize_hidden_fields(self) -> None:
        for field_name in PAIR_FIELD_NAMES:
            self.field_vars[field_name] = tk.StringVar(value="")
        self.field_vars["on_dialysis"] = tk.BooleanVar(value=False)
        self.field_vars["on_lipid_lowering_medication"] = tk.BooleanVar(value=False)
        self.field_vars["on_statin_medication"] = tk.BooleanVar(value=False)

    def _build_ui(self) -> None:
        self.master.title(f"新制降膽固醇藥物健保給付助理 v{__version__}")
        icon_path = bundled_resource_path("assets/statin_nhi.ico")
        if sys.platform == "win32" and icon_path.exists():
            self.master.iconbitmap(str(icon_path))
        self.master.geometry("1240x740")
        self.master.minsize(1100, 700)

        self.grid_columnconfigure(0, weight=4, minsize=440)
        self.grid_columnconfigure(1, weight=5, minsize=600)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 10), pady=14)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        left.grid_rowconfigure(3, weight=3)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=14)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        note_frame = ctk.CTkFrame(left, corner_radius=14, fg_color="#F8FAFC", border_width=1, border_color="#D7E1EC")
        note_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        note_frame.grid_columnconfigure(0, weight=1)
        note_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            note_frame,
            text="貼上病歷診斷及用藥",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=16, weight="bold"),
            text_color="#16324F",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 5))

        self.note_text = ctk.CTkTextbox(note_frame, height=100, font=("Consolas", 13), corner_radius=10)
        self.note_text.grid(row=1, column=0, sticky="nsew", padx=12)

        button_row = ctk.CTkFrame(note_frame, fg_color="transparent")
        button_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 10))

        button_font = action_button_font()
        ctk.CTkButton(button_row, text="帶入", command=self.parse_note_into_form, width=84, height=BUTTON_HEIGHT, font=button_font, fg_color="#0F8B8D", hover_color="#0B6D6E").pack(side="left")
        ctk.CTkButton(button_row, text="清除", command=self.clear_all, width=84, height=BUTTON_HEIGHT, font=button_font, fg_color="#D8E2EC", text_color="#143047", hover_color="#C9D5E0").pack(side="left", padx=(8, 0))
        ctk.CTkButton(button_row, text="判定", command=self.evaluate_patient, width=84, height=BUTTON_HEIGHT, font=button_font, fg_color="#1D6FD6", hover_color="#1557AA").pack(side="left", padx=(8, 0))

        result_frame = ctk.CTkFrame(left, corner_radius=14, fg_color="#F8FAFC", border_width=1, border_color="#D7E1EC")
        result_frame.grid(row=3, column=0, sticky="nsew")
        result_frame.grid_columnconfigure(0, weight=1)
        result_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            result_frame,
            text="健保給付判定結果",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=16, weight="bold"),
            text_color="#16324F",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 5))

        self.result_text = ctk.CTkTextbox(
            result_frame,
            font=ctk.CTkFont(family="Microsoft JhengHei", size=15),
            corner_radius=10,
        )
        self.result_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        result_button_row = ctk.CTkFrame(result_frame, fg_color="transparent")
        result_button_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        ctk.CTkButton(
            result_button_row,
            text="關於",
            command=self.open_about,
            width=84,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#D8E2EC",
            text_color="#143047",
            hover_color="#C9D5E0",
        ).pack(side="left")
        ctk.CTkButton(
            result_button_row,
            text="藥品",
            command=self.open_hospital_medication_matcher,
            width=84,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#0F8B8D",
            hover_color="#0B6D6E",
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            result_button_row,
            text="篩檢",
            command=self.open_fh_screening,
            width=84,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#C76B12",
            hover_color="#9E520C",
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            result_button_row,
            text="複製",
            command=self.copy_result_summary,
            width=84,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#1D6FD6",
            hover_color="#1557AA",
        ).pack(side="left", padx=(8, 0))

        scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        row_index = 0
        common_frame = self._add_section(scroll, row_index, "基本資料", "性別、年齡、LDL-C、總膽固醇")
        row_index += 1
        self._build_common_section(common_frame)

        extreme_frame = self._add_section(
            scroll,
            row_index,
            "極高風險 / 非常高風險",
            "先從這一區判斷；若已符合極高風險，後面區塊原則上可不必再填。",
            risk_section_key="extreme_very_high",
        )
        self.section_frames["extreme_very_high"] = extreme_frame
        row_index += 1
        current_row = extreme_frame.first_row
        self._build_checkbox_matrix(
            extreme_frame,
            current_row,
            [
                [("recent_mi_within_1y", "一年內心肌梗塞"), ("recurrent_mi", "多次心肌梗塞")],
                [("multivessel_coronary_disease", "多支冠狀動脈阻塞"), ("ascvd_history", "冠狀動脈疾病 (CAD)")],
                [("acute_coronary_syndrome", "急性冠心症病史"), ("coronary_revascularization", "接受過 PCI / CABG")],
                [("peripheral_arterial_disease", "周邊動脈疾病"), ("carotid_stenosis", "頸動脈狹窄")],
                [("peripheral_stenosis_ge_50", "周邊動脈狹窄 >= 50%"), ("carotid_stenosis_ge_50", "頸動脈狹窄 >= 50%")],
                [("coronary_stenosis_ge_50", "冠狀動脈狹窄 >= 50%"), ("ischemic_stroke_tia", "缺血性中風 / TIA")],
                [("diabetes", "糖尿病")],
            ],
        )

        high_frame = self._add_section(
            scroll,
            row_index,
            "高風險",
            "若前面未符合極高 / 非常高，再看這一區。CKD 需要兩次相隔至少 3 個月的報告。",
            risk_section_key="high",
        )
        self.section_frames["high"] = high_frame
        row_index += 1
        current_row = high_frame.first_row
        self._build_value_card(high_frame, current_row, "冠狀動脈鈣化分數 (CAC)", "cac_score")
        self._build_single_checkbox_row(
            high_frame,
            current_row + 1,
            "ckd_persistent_3m",
            "進入透析前的慢性腎臟病 (eGFR<60 或 UACR>=30 至少三個月)",
        )
        self.field_widgets["ckd_persistent_3m"].configure(command=self._confirm_ckd_override_if_needed)
        self._build_report_table(
            high_frame,
            current_row + 2,
            [
                ("eGFR", "egfr_value_1", "egfr_date_1", "egfr_value_2", "egfr_date_2"),
                ("UACR", "uacr_value_1", "uacr_date_1", "uacr_value_2", "uacr_date_2"),
            ],
        )

        moderate_frame = self._add_section(
            scroll,
            row_index,
            "中風險 / 低風險 / 零危險因子",
            "",
            risk_section_key="moderate_low_minimal",
        )
        self.section_frames["moderate_low_minimal"] = moderate_frame
        row_index += 1
        current_row = moderate_frame.first_row
        current_row = self._build_checkbox_matrix(
            moderate_frame,
            current_row,
            [
                [("hypertension", "高血壓"), ("smoking", "目前吸菸")],
                [("family_history_early_cad", "早發性冠心病家族史 (男<=55或女<=65)"), ("metabolic_syndrome", "代謝症候群")],
            ],
        )
        self._build_metabolic_inputs(moderate_frame, current_row)
        self._set_active_risk_section("extreme_very_high")

    def _add_section(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        title: str,
        note: str,
        risk_section_key: str | None = None,
    ) -> SectionFrame:
        on_toggle = None if risk_section_key is None else lambda: self._set_active_risk_section(risk_section_key)
        frame = SectionFrame(parent, title, note, on_toggle=on_toggle)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        return frame

    def _build_common_section(self, frame: SectionFrame) -> None:
        row = frame.first_row
        input_row = ctk.CTkFrame(frame, fg_color="#F2F7FB", corner_radius=14)
        input_row.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 12))
        for column in range(4):
            input_row.grid_columnconfigure(column, weight=1)

        fields = [
            ("性別", "sex", "choice"),
            ("年齡", "age", "number"),
            ("LDL-C", "ldl_c", "number"),
            ("總膽固醇", "total_cholesterol", "number"),
        ]
        for column, (label, field_name, field_type) in enumerate(fields):
            cell = ctk.CTkFrame(input_row, fg_color="transparent")
            cell.grid(row=0, column=column, sticky="ew", padx=10, pady=10)
            ctk.CTkLabel(
                cell,
                text=label,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13, weight="bold"),
                text_color="#526A81",
            ).pack(anchor="w", pady=(0, 5))
            self.field_vars[field_name] = tk.StringVar(value="")
            if field_type == "choice":
                widget = ctk.CTkComboBox(cell, values=["", "男", "女"], variable=self.field_vars[field_name], width=112, height=30, state="readonly")
            else:
                widget = ctk.CTkEntry(cell, textvariable=self.field_vars[field_name], width=112, height=30)
            widget.pack(fill="x")
            self.field_widgets[field_name] = widget

    def _build_checkbox_matrix(
        self,
        frame: SectionFrame,
        row: int,
        rows: list[list[tuple[str, str] | tuple[str, str, str]]],
    ) -> int:
        """Render every risk row on the same two grid columns."""
        matrix = ctk.CTkFrame(frame, fg_color="transparent")
        matrix.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 10))
        matrix.grid_columnconfigure(0, weight=1, uniform="risk_card")
        matrix.grid_columnconfigure(1, weight=1, uniform="risk_card")

        for matrix_row, items in enumerate(rows):
            matrix.grid_rowconfigure(matrix_row, weight=0)
            for column, item in enumerate(items):
                self._add_checkbox_card(matrix, matrix_row, column, item)
        return row + 1

    def _add_checkbox_card(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        item: tuple[str, str] | tuple[str, str, str],
    ) -> None:
        field_name, label = item[0], item[1]
        detail = item[2] if len(item) == 3 else ""
        self.field_vars[field_name] = tk.BooleanVar(value=False)
        card = ctk.CTkFrame(parent, fg_color="#EDF4FA", corner_radius=14, border_width=1, border_color="#D7E1EC")
        card.grid(row=row, column=column, sticky="nsew", padx=(0, 10) if column == 0 else 0, pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        checkbox = ctk.CTkCheckBox(
            card,
            text="",
            variable=self.field_vars[field_name],
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            text_color="#18354E",
            checkbox_width=20,
            checkbox_height=20,
            width=24,
        )
        checkbox.grid(row=0, column=0, sticky="nw", padx=(12, 8), pady=12)
        text_cell = ctk.CTkFrame(card, fg_color="transparent")
        text_cell.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=10)
        ctk.CTkLabel(
            text_cell,
            text=label,
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            text_color="#18354E",
            justify="left",
            wraplength=205,
        ).pack(anchor="w")
        if detail:
            ctk.CTkLabel(
                text_cell,
                text=detail,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=11),
                text_color="#61768C",
            ).pack(anchor="w", pady=(2, 0))
        self.field_widgets[field_name] = checkbox

    def _build_single_checkbox_row(self, frame: SectionFrame, row: int, field_name: str, label: str) -> int:
        self.field_vars[field_name] = tk.BooleanVar(value=False)
        card = ctk.CTkFrame(frame, fg_color="#EDF4FA", corner_radius=14, border_width=1, border_color="#D7E1EC")
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        checkbox = ctk.CTkCheckBox(
            card,
            text="",
            variable=self.field_vars[field_name],
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            text_color="#18354E",
            checkbox_width=20,
            checkbox_height=20,
            width=24,
        )
        checkbox.grid(row=0, column=0, sticky="nw", padx=(12, 8), pady=12)
        label_widget = ctk.CTkLabel(
            card,
            text=label,
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            text_color="#18354E",
            justify="left",
            wraplength=500,
        )
        label_widget.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=12)
        self.field_widgets[field_name] = checkbox
        return row + 1

    def _build_choice_row(self, frame: SectionFrame, row: int, label: str, field_name: str, values: list[str]) -> None:
        self.field_vars[field_name] = tk.StringVar(value="")
        row_frame = self._build_compact_input_row(frame, row, label)
        widget = ctk.CTkComboBox(row_frame, values=values, variable=self.field_vars[field_name], width=140, state="readonly")
        widget.grid(row=0, column=1, sticky="w")
        self.field_widgets[field_name] = widget

    def _build_number_row(self, frame: SectionFrame, row: int, label: str, field_name: str) -> None:
        self.field_vars[field_name] = tk.StringVar(value="")
        row_frame = self._build_compact_input_row(frame, row, label)
        widget = ctk.CTkEntry(row_frame, textvariable=self.field_vars[field_name], width=130)
        widget.grid(row=0, column=1, sticky="w")
        self.field_widgets[field_name] = widget

    def _build_value_card(self, frame: SectionFrame, row: int, label: str, field_name: str) -> None:
        self.field_vars[field_name] = tk.StringVar(value="")
        card = ctk.CTkFrame(frame, fg_color="#EDF4FA", corner_radius=14, border_width=1, border_color="#D7E1EC")
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text=label,
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            text_color="#18354E",
        ).grid(row=0, column=0, sticky="w", padx=(12, 16), pady=12)
        widget = ctk.CTkEntry(card, textvariable=self.field_vars[field_name], width=110, height=32)
        widget.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=10)
        self.field_widgets[field_name] = widget

    def _build_compact_input_row(self, frame: SectionFrame, row: int, label: str) -> ctk.CTkFrame:
        row_frame = ctk.CTkFrame(frame, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 10))
        row_frame.grid_columnconfigure(0, minsize=120)
        ctk.CTkLabel(
            row_frame,
            text=label,
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            text_color="#18354E",
        ).grid(row=0, column=0, sticky="w")
        return row_frame

    def _build_report_table(
        self,
        frame: SectionFrame,
        row: int,
        rows: list[tuple[str, str, str, str, str]],
    ) -> None:
        table = ctk.CTkFrame(frame, fg_color="#F2F7FB", corner_radius=14)
        table.grid(row=row, column=0, sticky="ew", padx=18, pady=(2, 14))
        widths = (100, 74, 94, 74, 94)
        for column, width in enumerate(widths):
            table.grid_columnconfigure(column, minsize=width, weight=1 if column in (0, 2, 4) else 0)

        for column, header in enumerate(("項目", "數值 1", "日期 1", "數值 2", "日期 2")):
            ctk.CTkLabel(
                table,
                text=header,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=12, weight="bold"),
                text_color="#61768C",
            ).grid(row=0, column=column, sticky="w", padx=(12 if column == 0 else 6, 6), pady=(10, 8))

        for table_row, (label, value_1, date_1, value_2, date_2) in enumerate(rows, start=1):
            ctk.CTkLabel(table, text=label, font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14), text_color="#18354E").grid(
                row=table_row, column=0, sticky="w", padx=(12, 6), pady=5
            )
            for column, field_name, width in ((1, value_1, 68), (2, date_1, 88), (3, value_2, 68), (4, date_2, 88)):
                entry = ctk.CTkEntry(table, textvariable=self.field_vars[field_name], width=width, height=30)
                entry.grid(row=table_row, column=column, sticky="w", padx=6, pady=5)
                self.field_widgets[field_name] = entry

    def _build_metabolic_inputs(self, frame: SectionFrame, row: int) -> None:
        top_row = ctk.CTkFrame(frame, fg_color="#F2F7FB", corner_radius=14)
        top_row.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 10))
        bottom_row = ctk.CTkFrame(frame, fg_color="#F2F7FB", corner_radius=14)
        bottom_row.grid(row=row + 1, column=0, sticky="ew", padx=18, pady=(0, 14))
        for row_frame in (top_row, bottom_row):
            for column in range(3):
                row_frame.grid_columnconfigure(column, weight=1)

        self._build_metric_input_cell(top_row, 0, "腹圍", "waist_cm")
        self._build_metric_input_cell(top_row, 1, "血壓", "bp_text", placeholder="例如 130/85")
        self._build_metric_input_cell(top_row, 2, "空腹血糖", "fasting_glucose")
        self._build_tg_medication_cell(bottom_row, 0)
        self._build_metric_input_cell(bottom_row, 1, "空腹 TG", "triglycerides")
        self._build_metric_input_cell(bottom_row, 2, "HDL-C", "hdl_c")

    def _build_metric_input_cell(
        self, parent: ctk.CTkFrame, column: int, label: str, field_name: str, placeholder: str = ""
    ) -> None:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13, weight="bold"), text_color="#526A81").pack(
            anchor="w", pady=(0, 5)
        )
        self.field_vars[field_name] = tk.StringVar(value="")
        entry = ctk.CTkEntry(cell, textvariable=self.field_vars[field_name], width=112, height=30, placeholder_text=placeholder)
        entry.pack(fill="x")
        self.field_widgets[field_name] = entry

    def _build_tg_medication_cell(self, parent: ctk.CTkFrame, column: int) -> None:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(cell, text="高 TG 已用藥", font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13, weight="bold"), text_color="#526A81").pack(
            anchor="w", pady=(0, 7)
        )
        self.field_vars["on_tg_medication"] = tk.StringVar(value="")
        widget = ctk.CTkComboBox(cell, values=["", "是", "否"], variable=self.field_vars["on_tg_medication"], width=112, height=30, state="readonly")
        widget.pack(anchor="w")
        self.field_widgets["on_tg_medication"] = widget

    def _build_measurement_table(
        self,
        frame: SectionFrame,
        row: int,
        rows: list[tuple[str, str | None, str, str, str, str]],
    ) -> None:
        table = ctk.CTkFrame(frame, fg_color="#F2F7FB", corner_radius=14)
        table.grid(row=row, column=0, sticky="ew", padx=18, pady=(2, 14))
        widths = (98, 66, 62, 84, 62, 84)
        for column, width in enumerate(widths):
            table.grid_columnconfigure(column, minsize=width, weight=1 if column in (0, 3, 5) else 0)

        headers = ("項目", "用藥", "數值 1", "日期 1", "數值 2", "日期 2")
        for column, header in enumerate(headers):
            ctk.CTkLabel(
                table,
                text=header,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=12, weight="bold"),
                text_color="#61768C",
            ).grid(row=0, column=column, sticky="w", padx=(12 if column == 0 else 6, 6), pady=(10, 8))

        for table_row, (label, med_field, value_1, date_1, value_2, date_2) in enumerate(rows, start=1):
            ctk.CTkLabel(
                table,
                text=label,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
                text_color="#18354E",
            ).grid(row=table_row, column=0, sticky="w", padx=(12, 6), pady=5)

            if med_field is not None:
                if med_field not in self.field_vars:
                    self.field_vars[med_field] = tk.BooleanVar(value=False)
                med_widget = ctk.CTkCheckBox(
                    table,
                    text="已用藥",
                    variable=self.field_vars[med_field],
                    checkbox_width=18,
                    checkbox_height=18,
                    font=ctk.CTkFont(family="Microsoft JhengHei UI", size=12),
                )
                med_widget.grid(row=table_row, column=1, sticky="w", padx=6, pady=5)
                self.field_widgets[med_field] = med_widget
            else:
                ctk.CTkLabel(table, text="-", text_color="#A0AFBC").grid(row=table_row, column=1, sticky="w", padx=8, pady=5)

            for column, field_name, width in ((2, value_1, 62), (3, date_1, 80), (4, value_2, 62), (5, date_2, 80)):
                if field_name not in self.field_vars:
                    self.field_vars[field_name] = tk.StringVar(value="")
                entry = ctk.CTkEntry(table, textvariable=self.field_vars[field_name], width=width, height=30)
                entry.grid(row=table_row, column=column, sticky="w", padx=6, pady=5)
                self.field_widgets[field_name] = entry

    def _bind_dynamic_updates(self) -> None:
        for field_name in (
            "sex",
            "age",
            "recent_mi_within_1y",
            "recurrent_mi",
            "multivessel_coronary_disease",
            "ascvd_history",
            "acute_coronary_syndrome",
            "coronary_revascularization",
            "coronary_stenosis_ge_50",
            "carotid_stenosis_ge_50",
            "ischemic_stroke_tia",
            "peripheral_arterial_disease",
            "diabetes",
            "ckd_persistent_3m",
            "ldl_c",
            "cac_score",
            "hypertension",
            "on_tg_medication",
            "on_lipid_lowering_medication",
            "on_statin_medication",
        ):
            variable = self.field_vars.get(field_name)
            if variable is not None:
                variable.trace_add("write", self._on_dynamic_field_changed)

    def _on_dynamic_field_changed(self, *_args: object) -> None:
        self._refresh_derived_egfr()
        self.refresh_dynamic_ui()

    def _refresh_derived_egfr(self) -> None:
        """Keep creatinine-derived eGFR-EPI synchronized with sex and age edits."""
        if not self._egfr_derived_from_creatinine or self._updating_derived_egfr:
            return
        age = self._float_or_none("age")
        sex = {"男": "male", "女": "female"}.get(self.field_vars["sex"].get().strip(), "")
        reports = []
        for value_field, date_field in (
            ("creatinine_past", "creatinine_past_date"),
            ("creatinine_latest", "creatinine_latest_date"),
        ):
            value = self._float_or_none(value_field)
            report_date = parse_clinical_date(self.field_vars[date_field].get())
            if value is not None and report_date is not None:
                reports.append((report_date, value))
        reports = sorted(dict(reports).items())[-2:]

        self._updating_derived_egfr = True
        try:
            for field_name in ("egfr_value_1", "egfr_date_1", "egfr_value_2", "egfr_date_2"):
                self.field_vars[field_name].set("")
            if age is None or not sex:
                return
            estimates = [
                (report_date, _estimate_egfr_epi_2021(creatinine, age, sex))
                for report_date, creatinine in reports
            ]
            estimates = [(report_date, estimate) for report_date, estimate in estimates if estimate is not None]
            for index, (report_date, estimate) in enumerate(estimates, start=3 - len(estimates)):
                self.field_vars[f"egfr_value_{index}"].set(f"{estimate:.1f}")
                self.field_vars[f"egfr_date_{index}"].set(format_roc_date(report_date))
        finally:
            self._updating_derived_egfr = False

    def _float_or_none(self, field_name: str) -> float | None:
        raw = self.field_vars[field_name].get().strip()
        if not raw:
            return None
        try:
            return parse_nonnegative_number(raw)
        except ValueError:
            return None

    def _parse_bp_text(self, field_name: str) -> tuple[float | None, float | None]:
        raw = self.field_vars[field_name].get().strip()
        if not raw or "/" not in raw:
            return None, None
        left, right = raw.split("/", 1)
        try:
            return parse_nonnegative_number(left), parse_nonnegative_number(right)
        except ValueError:
            return None, None

    def _validate_numeric_inputs(self) -> None:
        errors = []
        for name, label in NUMERIC_LABELS.items():
            try:
                parse_nonnegative_number(self.field_vars[name].get())
            except ValueError:
                errors.append(label)
        raw_bp = self.field_vars["bp_text"].get().strip()
        if raw_bp:
            try:
                parts = raw_bp.split("/")
                if len(parts) != 2 or any(parse_nonnegative_number(part) is None for part in parts):
                    raise ValueError("血壓格式錯誤")
            except ValueError:
                errors.append("血壓（收縮壓/舒張壓）")
        if errors:
            raise ValueError("請修正以下欄位：" + "、".join(errors) + "。請輸入有限且不小於零的數字。")

    def _current_priority_level(self) -> str:
        coronary_condition = any(
            bool(self.field_vars[name].get())
            for name in (
                "ascvd_history",
                "recent_mi_within_1y",
                "recurrent_mi",
                "multivessel_coronary_disease",
                "acute_coronary_syndrome",
                "coronary_revascularization",
                "coronary_stenosis_ge_50",
            )
        )
        if any(bool(self.field_vars[name].get()) for name in ("recent_mi_within_1y", "recurrent_mi", "multivessel_coronary_disease")):
            return "extreme"
        if bool(self.field_vars["acute_coronary_syndrome"].get()) and bool(self.field_vars["diabetes"].get()):
            return "extreme"
        if coronary_condition and any(bool(self.field_vars[name].get()) for name in ("peripheral_arterial_disease", "carotid_stenosis")):
            return "extreme"
        if bool(self.field_vars["ischemic_stroke_tia"].get()) and (
            coronary_condition
            or bool(self.field_vars["peripheral_arterial_disease"].get())
            or bool(self.field_vars["carotid_stenosis"].get())
        ):
            return "very_high"
        if any(
            bool(self.field_vars[name].get())
            for name in (
                "acute_coronary_syndrome",
                "coronary_revascularization",
                "peripheral_arterial_disease",
                "coronary_stenosis_ge_50",
                "peripheral_stenosis_ge_50",
                "carotid_stenosis_ge_50",
            )
        ):
            return "very_high"
        ldl_value = self._float_or_none("ldl_c")
        cac_value = self._float_or_none("cac_score")
        if bool(self.field_vars["diabetes"].get()) or bool(self.field_vars["ckd_persistent_3m"].get()) or (ldl_value is not None and ldl_value >= 190) or (cac_value is not None and cac_value >= 400):
            return "high"
        return "moderate_or_lower"

    def _set_section_state(self, frame: SectionFrame, enabled: bool) -> None:
        for child in frame.winfo_children():
            if isinstance(child, (ctk.CTkFrame, SectionFrame)):
                self._set_section_state(child, enabled)
                continue
            try:
                child.configure(state="normal" if enabled else "disabled")
            except (tk.TclError, ValueError):
                continue

    def _set_active_risk_section(self, section_key: str) -> None:
        """Keep one risk section open while preserving each section's grid layout."""
        self.active_risk_section = section_key
        for key in self.risk_section_keys:
            frame = self.section_frames.get(key)
            if frame is not None:
                frame.set_expanded(key == section_key)

    def _set_fields_enabled(self, field_names: list[str], enabled: bool) -> None:
        for field_name in field_names:
            widget = self.field_widgets.get(field_name)
            if widget is None:
                continue
            try:
                widget.configure(state="normal" if enabled else "disabled")
            except (tk.TclError, ValueError):
                continue

    def _sync_auto_derived_checkbox(self, field_name: str, should_be_checked: bool) -> None:
        """Only undo a value when this app, rather than the user, derived it."""
        variable = self.field_vars[field_name]
        if should_be_checked:
            if not bool(variable.get()):
                self._auto_derived_fields.add(field_name)
                variable.set(True)
        elif field_name in self._auto_derived_fields:
            self._auto_derived_fields.remove(field_name)
            variable.set(False)

    def refresh_dynamic_ui(self) -> None:
        derived_acs = any(
            bool(self.field_vars[name].get()) for name in ("recent_mi_within_1y", "recurrent_mi")
        )
        self._sync_auto_derived_checkbox("acute_coronary_syndrome", derived_acs)

        derived_cad = any(
            bool(self.field_vars[name].get())
            for name in (
                "recent_mi_within_1y",
                "recurrent_mi",
                "multivessel_coronary_disease",
                "acute_coronary_syndrome",
                "coronary_revascularization",
                "coronary_stenosis_ge_50",
            )
        )
        self._sync_auto_derived_checkbox("ascvd_history", derived_cad)
        self._sync_auto_derived_checkbox("carotid_stenosis", bool(self.field_vars["carotid_stenosis_ge_50"].get()))

        # Risk priority controls which section is open, not whether supplementary
        # lipid data can be entered.  TC/HDL-C remain available for non-HDL-C.
        for section_key in self.risk_section_keys:
            self._set_section_state(self.section_frames[section_key], True)

        level = self._current_priority_level()
        if level == "extreme":
            self._set_active_risk_section("extreme_very_high")
            self.risk_hint_var.set("目前已命中極高風險；如需 non-HDL-C，仍可展開下方區塊補填 HDL-C。")
        elif level == "very_high":
            self._set_active_risk_section("extreme_very_high")
            self.risk_hint_var.set("目前已命中非常高風險；如需 non-HDL-C，仍可展開下方區塊補填 HDL-C。")
        elif level == "high":
            self._set_active_risk_section("high")
            self.risk_hint_var.set("目前至少已到高風險；仍可展開下方區塊補填 HDL-C。")
        else:
            self.risk_hint_var.set("目前需要繼續判斷中風險 / 低風險 / 零危險因子。")

    def _has_qualifying_ckd_pair(self) -> bool:
        def has_pair(value_1: str, date_1: str, value_2: str, date_2: str, threshold) -> bool:
            first = self._float_or_none(value_1)
            second = self._float_or_none(value_2)
            if first is None or second is None:
                return False
            first_date = parse_clinical_date(self.field_vars[date_1].get())
            second_date = parse_clinical_date(self.field_vars[date_2].get())
            if first_date is None or second_date is None:
                return False
            gap = abs((second_date - first_date).days)
            return gap >= 90 and threshold(first) and threshold(second)

        return has_pair("egfr_value_1", "egfr_date_1", "egfr_value_2", "egfr_date_2", lambda value: value < 60) or has_pair(
            "uacr_value_1", "uacr_date_1", "uacr_value_2", "uacr_date_2", lambda value: value >= 30
        )

    def _confirm_ckd_override_if_needed(self) -> None:
        if not bool(self.field_vars["ckd_persistent_3m"].get()):
            return
        if bool(self.field_vars["on_dialysis"].get()):
            messagebox.showwarning("慢性腎臟病確認", "病歷顯示正在接受透析／洗腎，不符合進入透析前的慢性腎臟病條件。")
            self.field_vars["ckd_persistent_3m"].set(False)
            return
        if self._has_qualifying_ckd_pair():
            return
        confirmed = messagebox.askyesno("慢性腎臟病確認", "確定符合進入透析前的慢性腎臟病？")
        if not confirmed:
            self.field_vars["ckd_persistent_3m"].set(False)

    def parse_note_into_form(self) -> None:
        parse_result = parse_note(
            self.note_text.get("1.0", "end").strip(),
            fallback_sex=self.field_vars["sex"].get(),
            fallback_age=self._float_or_none("age"),
        )
        remap = {
            "sex": "sex",
            "egfr": "egfr_value_2",
            "egfr_date": "egfr_date_2",
            "uacr": "uacr_value_2",
        }
        for field_name, value in parse_result.extracted_fields.items():
            if field_name == "systolic_bp":
                diastolic = parse_result.extracted_fields.get("diastolic_bp")
                if diastolic is not None:
                    systolic_text = int(value) if float(value).is_integer() else value
                    diastolic_text = int(diastolic) if float(diastolic).is_integer() else diastolic
                    self.field_vars["bp_text"].set(f"{systolic_text}/{diastolic_text}")
                continue
            if field_name == "diastolic_bp":
                continue
            target = remap.get(field_name, field_name)
            if target == "sex":
                value = {"male": "男", "female": "女"}.get(str(value), value)
            if target == "on_tg_medication":
                value = "是" if bool(value) else "否"
            if target not in self.field_vars:
                continue
            variable = self.field_vars[target]
            if isinstance(variable, tk.BooleanVar):
                variable.set(bool(value))
            else:
                variable.set(str(int(value)) if isinstance(value, float) and value.is_integer() else str(value))
        self._egfr_derived_from_creatinine = parse_result.extracted_fields.get("egfr_source") == "creatinine"
        self._refresh_derived_egfr()
        self._confirm_ckd_override_if_needed()
        self.refresh_dynamic_ui()

    def clear_all(self) -> None:
        self.note_text.delete("1.0", "end")
        self.result_text.delete("1.0", "end")
        self.fh_screening_data = None
        for variable in self.field_vars.values():
            if isinstance(variable, tk.BooleanVar):
                variable.set(False)
            else:
                variable.set("")
        self.refresh_dynamic_ui()

    def open_about(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("關於")
        dialog.geometry("540x570")
        dialog.minsize(540, 450)
        dialog.resizable(True, True)
        dialog.grid_rowconfigure(1, weight=1)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text=f"新制降膽固醇藥物健保給付助理 v{__version__}",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=17, weight="bold"),
            text_color="#16324F",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 14))

        body = ctk.CTkScrollableFrame(dialog, fg_color="#F8FAFC", corner_radius=14, border_width=1, border_color="#D7E1EC")
        body.grid(row=1, column=0, sticky="nsew", padx=18)
        body.grid_columnconfigure(0, weight=1)
        heading_font = ctk.CTkFont(family="Microsoft JhengHei UI", size=14, weight="bold")
        text_font = ctk.CTkFont(family="Microsoft JhengHei UI", size=14)

        sections = [
            (
                "給付規定更新依據",
                "115-10-29：健保審字第1150672925號\n"
                "生效日期：115-12-01\n"
                "本次更新範圍：2.6.1、2.6.3 藥品給付規定。",
            ),
            (
                "用途",
                "協助整理病歷與手動輸入資料，提供 ASCVD 風險分級、血脂目標及院內新制藥物清單，供使用者確認。",
            ),
            (
                "資料與隱私",
                "病歷文字與病人輸入資料不會自動儲存。\n"
                "院內藥物設定與公告提醒偏好，儲存於程式同資料夾的 Statin_NHI_available.json。\n"
                "藥物清單依台灣當日日期篩選給付生效品項。",
            ),
            (
                "使用提醒",
                "本程式未完整驗證個別藥品的前置療程、事前審查及所有給付條件；最終仍須依現行健保規定、病歷證據與院內流程確認。",
            ),
        ]
        for row, (heading, text) in enumerate(sections):
            ctk.CTkLabel(body, text=heading, font=heading_font, text_color="#16324F").grid(
                row=row * 2,
                column=0,
                sticky="w",
                padx=16,
                pady=(12 if row == 0 else 8, 2),
            )
            ctk.CTkLabel(
                body,
                text=text,
                font=text_font,
                text_color="#18354E",
                justify="left",
                anchor="w",
                wraplength=430,
            ).grid(row=row * 2 + 1, column=0, sticky="w", padx=16)

        feedback_row = len(sections) * 2
        ctk.CTkLabel(body, text="意見回饋", font=heading_font, text_color="#16324F").grid(
            row=feedback_row,
            column=0,
            sticky="w",
            padx=16,
            pady=(8, 2),
        )
        feedback = ctk.CTkFrame(body, fg_color="transparent")
        feedback.grid(row=feedback_row + 1, column=0, sticky="w", padx=16)
        feedback_url = "https://forms.gle/Fm9NTQF7eaKczPF36"
        link_label = ctk.CTkLabel(
            feedback,
            text=feedback_url,
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14, underline=True),
            text_color="#1D6FD6",
            anchor="w",
        )
        link_label.pack(anchor="w")
        link_label.bind("<Button-1>", lambda _event: webbrowser.open_new_tab(feedback_url))
        ctk.CTkLabel(
            feedback,
            text="花蓮慈濟家醫科王啟忠醫師",
            font=text_font,
            text_color="#18354E",
            anchor="w",
        ).pack(anchor="w")

        def close() -> None:
            dialog.grab_release()
            dialog.destroy()

        ctk.CTkButton(
            dialog,
            text="關閉",
            command=close,
            width=90,
            height=BUTTON_HEIGHT,
            font=action_button_font(),
            fg_color="#D8E2EC",
            text_color="#143047",
            hover_color="#C9D5E0",
        ).grid(row=2, column=0, sticky="e", padx=18, pady=16)

    def show_medication_update(self) -> None:
        reminder_path = self.medication_settings_path
        if self.medication_catalog_error or not should_show_medication_update(
            self.hospital_medication_codes, reminder_path
        ):
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("新增健保給付藥物提醒")
        dialog.geometry("720x570")
        dialog.minsize(660, 520)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            dialog, text="2026/12/1 新增健保新制給付藥物",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=20, weight="bold"),
            text_color="#16324F",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 12))
        body_font = ctk.CTkFont(family="Microsoft JhengHei UI", size=14, weight="bold")
        listing = ctk.CTkTextbox(dialog, wrap="word", font=body_font, text_color="#000000")
        listing.grid(row=1, column=0, sticky="nsew", padx=24)
        items = self.medication_catalog.selected(list(NEW_MEDICATION_CODES))
        listing.insert("1.0", "以下品項尚未加入您的院內藥物設定：\n\n" + "\n\n".join(
            f"• {item.display_label}｜{item.code}" for item in items
        ))
        listing.configure(state="disabled")
        ctk.CTkLabel(
            dialog, text="若其中有院內可使用的藥物，請至「藥物設定」新增。\n"
            "可預先設定；2026/12/1 起才列入新制可用輸出。",
            justify="left", anchor="w", wraplength=610,
            font=body_font, text_color="#000000",
        ).grid(row=2, column=0, sticky="w", padx=24, pady=12)
        dismissed = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            dialog, text="不再提醒本次新增品項", variable=dismissed,
            font=body_font, text_color="#000000",
        ).grid(
            row=3, column=0, sticky="w", padx=24, pady=(0, 12)
        )

        def close(open_settings: bool = False) -> None:
            if dismissed.get():
                try:
                    dismiss_medication_update(reminder_path)
                except OSError as error:
                    messagebox.showerror("無法儲存提醒設定", f"本次提醒偏好尚未儲存：\n{error}\n請確認設定檔格式正確且資料夾可寫入。", parent=dialog)
                    return
            dialog.grab_release()
            dialog.destroy()
            if open_settings:
                self.open_hospital_medication_matcher()

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="e", padx=24, pady=(0, 20))
        button_font = action_button_font()
        ctk.CTkButton(
            buttons, text="稍後設定", command=close,
            width=110, height=BUTTON_HEIGHT, font=button_font,
            fg_color="#C83D3D", hover_color="#A82F2F",
        ).pack(side="left")
        ctk.CTkButton(
            buttons, text="開啟藥物設定", command=lambda: close(True),
            width=140, height=BUTTON_HEIGHT, font=button_font,
            fg_color="#1D6FD6", hover_color="#1557AA",
        ).pack(side="left", padx=(8, 0))
        dialog.protocol("WM_DELETE_WINDOW", close)

    def open_hospital_medication_matcher(self) -> None:
        if self.medication_catalog_error is not None:
            messagebox.showerror("新制藥物主檔", self.medication_catalog_error, parent=self.master)
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("院內降膽固醇藥物比對")
        dialog.geometry("980x700")
        dialog.minsize(900, 560)
        dialog.resizable(True, True)
        dialog.grid_rowconfigure(2, weight=1)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text="院內降膽固醇藥物比對",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=17, weight="bold"),
            text_color="#16324F",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 3))
        ctk.CTkLabel(
            dialog,
            text="輸入院內健保代碼；未生效品項可預先儲存，生效日起才列入新制可用輸出。",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13),
            text_color="#526A81",
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 12))

        body = ctk.CTkScrollableFrame(dialog, fg_color="#F8FAFC", corner_radius=14, border_width=1, border_color="#D7E1EC")
        body.grid(row=2, column=0, sticky="nsew", padx=18)
        body.grid_columnconfigure(1, weight=1)
        header_font = ctk.CTkFont(family="Microsoft JhengHei UI", size=14, weight="bold")
        ctk.CTkLabel(body, text="健保代碼", font=header_font, text_color="#16324F").grid(row=0, column=0, sticky="w", padx=(16, 12), pady=(12, 5))
        ctk.CTkLabel(body, text="比對結果", font=header_font, text_color="#16324F").grid(row=0, column=1, sticky="w", padx=4, pady=(12, 5))

        ctk.CTkLabel(body, text="給付生效日期", font=header_font, text_color="#16324F").grid(row=0, column=2, sticky="w", padx=(12, 16), pady=(12, 5))

        date_variables = []
        date_labels = []
        code_variables = []
        result_variables = []
        for row_index in range(max(10, len(self.hospital_medication_codes))):
            code = self.hospital_medication_codes[row_index] if row_index < len(self.hospital_medication_codes) else ""
            code_variable = tk.StringVar(value=code)
            result_variable = tk.StringVar()
            code_variables.append(code_variable)
            result_variables.append(result_variable)
            ctk.CTkEntry(
                body,
                textvariable=code_variable,
                width=150,
                height=30,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
            ).grid(row=row_index + 1, column=0, sticky="w", padx=(16, 12), pady=3)
            ctk.CTkLabel(
                body,
                textvariable=result_variable,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13),
                text_color="#18354E",
                anchor="w",
                justify="left",
                wraplength=470,
            ).grid(row=row_index + 1, column=1, sticky="ew", padx=(4, 16), pady=3)

            date_variable = tk.StringVar()
            date_label = ctk.CTkLabel(
                body, textvariable=date_variable, width=175,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=13),
                anchor="w", justify="left",
            )
            date_label.grid(row=row_index + 1, column=2, sticky="w", padx=(12, 16), pady=3)
            date_variables.append(date_variable)
            date_labels.append(date_label)

        def validate_codes() -> list[str]:
            valid_codes = []
            seen: set[str] = set()
            for code_variable, result_variable, date_variable, date_label in zip(
                code_variables, result_variables, date_variables, date_labels, strict=True
            ):
                date_variable.set("")
                date_label.configure(text_color="#18354E")
                raw_code = code_variable.get().strip()
                code = normalize_medication_code(raw_code)
                medication = self.medication_catalog.lookup(code)
                if not raw_code:
                    result_variable.set("")
                elif medication is None:
                    result_variable.set("非新制可用藥物")
                elif medication.code in seen:
                    result_variable.set("重複代碼，不重複儲存")
                else:
                    valid_codes.append(medication.code)
                    seen.add(medication.code)
                    result_variable.set(f"✓ {medication.display_label}｜{medication.category}")
                    effective = medication.is_effective()
                    date_variable.set(
                        medication.effective_date.strftime("%Y/%m/%d")
                        + ("" if effective else "\n（未生效）")
                    )
                    date_label.configure(text_color="#18354E" if effective else "#B45309")
            return valid_codes

        def cancel() -> None:
            dialog.grab_release()
            dialog.destroy()

        def save() -> None:
            valid_codes = validate_codes()
            try:
                self.hospital_medication_codes = save_hospital_medication_codes(
                    self.medication_settings_path,
                    valid_codes,
                    self.medication_catalog,
                )
            except OSError as error:
                messagebox.showerror(
                    "無法儲存院內藥物設定",
                    f"設定尚未儲存：{error}\n\n請確認設定檔格式正確，並將程式置於可寫入的資料夾：\n{self.medication_settings_path.parent}",
                    parent=dialog,
                )
                return
            self.medication_settings_error = None
            if self.result_text.get("1.0", "end").strip():
                self.evaluate_patient()
            dialog.grab_release()
            dialog.destroy()

        validate_codes()
        button_row = ctk.CTkFrame(dialog, fg_color="transparent")
        button_row.grid(row=3, column=0, sticky="e", padx=18, pady=16)
        button_font = action_button_font()
        ctk.CTkButton(
            button_row,
            text="取消",
            command=cancel,
            width=90,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#C83D3D",
            hover_color="#A82F2F",
        ).pack(side="left")
        ctk.CTkButton(
            button_row,
            text="驗證",
            command=validate_codes,
            width=90,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#0F8B8D",
            hover_color="#0B6D6E",
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            button_row,
            text="儲存",
            command=save,
            width=90,
            height=BUTTON_HEIGHT,
            font=button_font,
            fg_color="#1D6FD6",
            hover_color="#1557AA",
        ).pack(side="left", padx=(8, 0))

    def open_fh_screening(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("FH 篩檢")
        dialog.geometry("590x620")
        dialog.resizable(False, False)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)

        current = self.fh_screening_data or FHScreeningData()
        field_names = [
            "first_degree_early_vascular_or_high_ldl",
            "first_degree_xanthoma_or_child_high_ldl",
            "personal_early_cad",
            "personal_early_cerebral_or_pad",
            "xanthoma",
            "corneal_arcus_under_45",
            "functional_gene_mutation",
        ]
        variables = {name: tk.BooleanVar(value=bool(getattr(current, name))) for name in field_names}
        result_var = tk.StringVar()

        ctk.CTkLabel(
            dialog,
            text="台灣家族性高膽固醇血症（FH）篩檢",
            font=ctk.CTkFont(family="Microsoft JhengHei UI", size=17, weight="bold"),
            text_color="#16324F",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 3))
        ctk.CTkLabel(
            dialog,
            textvariable=result_var,
            font=ctk.CTkFont(family="Microsoft JhengHei", size=14, weight="bold"),
            text_color="#1D6FD6",
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 14))

        body = ctk.CTkFrame(dialog, fg_color="#F8FAFC", corner_radius=14, border_width=1, border_color="#D7E1EC")
        body.grid(row=2, column=0, sticky="nsew", padx=18)
        body.grid_columnconfigure(0, weight=1)

        def add_heading(row: int, text: str) -> None:
            ctk.CTkLabel(
                body,
                text=text,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14, weight="bold"),
                text_color="#16324F",
            ).grid(row=row, column=0, sticky="w", padx=16, pady=(10, 3))

        def add_option(row: int, variable: tk.BooleanVar, text: str) -> None:
            option = ctk.CTkFrame(body, fg_color="transparent")
            option.grid(row=row, column=0, sticky="ew", padx=16, pady=2)
            option.grid_columnconfigure(1, weight=1)
            ctk.CTkCheckBox(option, text="", variable=variable, width=24, checkbox_width=18, checkbox_height=18).grid(
                row=0, column=0, sticky="nw", padx=(0, 8)
            )
            label = ctk.CTkLabel(
                option,
                text=text,
                font=ctk.CTkFont(family="Microsoft JhengHei UI", size=14),
                text_color="#18354E",
                justify="left",
                anchor="w",
                wraplength=480,
            )
            label.grid(row=0, column=1, sticky="ew")
            label.bind("<Button-1>", lambda _event, target=variable: target.set(not bool(target.get())))

        add_heading(0, "家族史（一等親：父母、兄弟姊妹、子女）")
        add_option(1, variables["first_degree_early_vascular_or_high_ldl"], "一等親早發性血管／冠狀動脈疾病，或 LDL-C > 160")
        add_option(2, variables["first_degree_xanthoma_or_child_high_ldl"], "一等親有黃色瘤／角膜弓，或 <18 歲一等親 LDL-C > 130")
        add_heading(3, "個人病史")
        add_option(4, variables["personal_early_cad"], "早發性冠狀動脈疾病（男 <45、女 <55）")
        add_option(5, variables["personal_early_cerebral_or_pad"], "早發性腦血管或周邊動脈疾病（男 <45、女 <55）")
        add_heading(6, "理學檢查")
        add_option(7, variables["xanthoma"], "黃色瘤 (xanthoma)")
        add_option(8, variables["corneal_arcus_under_45"], "角膜弓 (corneal arcus)，發生年齡 <45")
        add_heading(9, "基因檢測")
        add_option(10, variables["functional_gene_mutation"], "LDL-R、ApoB-100 或 PCSK9 功能性突變")
        ctk.CTkLabel(body, text="", height=10).grid(row=11, column=0, sticky="ew")
        ctk.CTkLabel(
            body,
            text="http://dx.doi.org/10.1016/j.jfma.2016.11.013",
            font=ctk.CTkFont(family="Microsoft JhengHei", size=12),
            text_color="#526A81",
        ).grid(row=12, column=0, sticky="w", padx=16, pady=(0, 12))

        def screening_data() -> FHScreeningData:
            return FHScreeningData(**{name: bool(variable.get()) for name, variable in variables.items()})

        def update_result(*_args: object) -> None:
            result_var.set(evaluate_fh_screening(screening_data(), self._float_or_none("ldl_c")).popup_text)

        for variable in variables.values():
            variable.trace_add("write", update_result)
        update_result()

        button_row = ctk.CTkFrame(dialog, fg_color="transparent")
        button_row.grid(row=3, column=0, sticky="e", padx=18, pady=16)
        dialog_button_font = action_button_font()

        def cancel_screening() -> None:
            dialog.grab_release()
            dialog.destroy()

        def finish_screening() -> None:
            self.fh_screening_data = screening_data()
            self.evaluate_patient()
            dialog.grab_release()
            dialog.destroy()

        ctk.CTkButton(
            button_row,
            text="取消",
            command=cancel_screening,
            width=90,
            height=BUTTON_HEIGHT,
            font=dialog_button_font,
            fg_color="#C83D3D",
            hover_color="#A82F2F",
        ).pack(side="left")
        ctk.CTkButton(button_row, text="完成", command=finish_screening, width=90, height=BUTTON_HEIGHT, font=dialog_button_font, fg_color="#1D6FD6", hover_color="#1557AA").pack(
            side="left", padx=(8, 0)
        )

    def build_patient_data(self) -> PatientData:
        self._validate_numeric_inputs()
        kwargs: dict[str, object] = {"note_text": self.note_text.get("1.0", "end").strip()}
        for field_name, _label, field_type, _choices in COMMON_FIELDS:
            if field_type == "choice":
                kwargs[field_name] = self.field_vars[field_name].get().strip()
            else:
                kwargs[field_name] = self._float_or_none(field_name)

        bool_fields = [
            "recent_mi_within_1y",
            "recurrent_mi",
            "multivessel_coronary_disease",
            "ascvd_history",
            "acute_coronary_syndrome",
            "coronary_revascularization",
            "peripheral_arterial_disease",
            "carotid_stenosis",
            "coronary_stenosis_ge_50",
            "peripheral_stenosis_ge_50",
            "carotid_stenosis_ge_50",
            "ischemic_stroke_tia",
            "diabetes",
            "ckd_persistent_3m",
            "on_dialysis",
            "family_history_early_cad",
            "metabolic_syndrome",
            "hypertension",
            "smoking",
            "on_tg_medication",
            "on_lipid_lowering_medication",
            "on_statin_medication",
        ]
        for field_name in bool_fields:
            if field_name == "on_tg_medication":
                kwargs[field_name] = self.field_vars[field_name].get() == "是"
            else:
                kwargs[field_name] = bool(self.field_vars[field_name].get())

        kwargs["arterial_stenosis_ge_50"] = any(
            bool(kwargs[field_name])
            for field_name in ("coronary_stenosis_ge_50", "peripheral_stenosis_ge_50", "carotid_stenosis_ge_50")
        )

        kwargs["cac_score"] = self._float_or_none("cac_score")
        for field_name in ("waist_cm", "fasting_glucose", "triglycerides", "hdl_c"):
            kwargs[field_name] = self._float_or_none(field_name)
        for field_name in PAIR_FIELD_NAMES:
            if field_name.endswith("_date_1") or field_name.endswith("_date_2") or field_name in ("creatinine_latest_date", "creatinine_past_date"):
                kwargs[field_name] = self.field_vars[field_name].get().strip()
            else:
                kwargs[field_name] = self._float_or_none(field_name)

        systolic_bp, diastolic_bp = self._parse_bp_text("bp_text")
        kwargs["systolic_bp"] = systolic_bp
        kwargs["diastolic_bp"] = diastolic_bp

        if kwargs.get("creatinine_latest") is not None and kwargs.get("creatinine_past") is not None:
            latest_date = str(kwargs.get("creatinine_latest_date", "") or "").strip()
            past_date = str(kwargs.get("creatinine_past_date", "") or "").strip()
            if latest_date and past_date:
                latest_obj = parse_clinical_date(latest_date)
                past_obj = parse_clinical_date(past_date)
                if latest_obj is not None and past_obj is not None:
                    kwargs["creatinine_month_gap"] = round(abs((latest_obj - past_obj).days) / 30.0, 1)

        return PatientData(**kwargs)

    def evaluate_patient(self) -> None:
        try:
            patient = self.build_patient_data()
        except ValueError as error:
            self.result_text.delete("1.0", "end")
            self.result_text.insert("1.0", f"輸入資料錯誤，尚未判讀。\n{error}")
            messagebox.showwarning("輸入資料錯誤", str(error))
            return
        outcomes = evaluate_all(patient)
        lines: list[str] = []
        for outcome in outcomes:
            lines.extend(self._format_eligibility_output(patient, outcome))
        if self.fh_screening_data is not None:
            fh_output = evaluate_fh_screening(self.fh_screening_data, patient.ldl_c).output_text
            try:
                divider_index = lines.index(OUTPUT_DIVIDER)
            except ValueError:
                lines.append(fh_output)
            else:
                lines.insert(divider_index, fh_output)
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "\n".join(lines))

    def copy_result_summary(self) -> None:
        result = self.result_text.get("1.0", "end").strip()
        if not result:
            return
        summary = result.split(OUTPUT_DIVIDER, maxsplit=1)[0].rstrip()
        self.clipboard_clear()
        self.clipboard_append(summary)
        self.update_idletasks()

    def _format_eligibility_output(self, patient: PatientData, outcome: RuleOutcome) -> list[str]:
        if not outcome.risk_category:
            return ["ASCVD 風險等級：無法判定", "缺少 LDL-C，無法進行健保給付分級。"]

        risk_category = outcome.risk_category
        conditions_suffix = ""
        if risk_category != "minimal":
            conditions = "、".join(outcome.matched_conditions) or "無"
            conditions_suffix = f"（{conditions}）"
        lines = [f"ASCVD 風險等級：{RISK_LABELS[risk_category]}{conditions_suffix}"]
        if outcome.status == "needs_review":
            lines[0] += "（暫定分級，需人工複核）"
        if outcome.missing_fields:
            lines.append("待補資料：" + "、".join(outcome.missing_fields))
        for note in outcome.follow_up_notes:
            lines.append("判讀提醒：" + note)

        ldl_threshold = outcome.ldl_start_threshold
        ldl_is_eligible = ldl_threshold is not None and patient.ldl_c is not None and patient.ldl_c >= ldl_threshold
        on_lipid_lowering_medication = patient.on_lipid_lowering_medication
        on_statin_medication = patient.on_statin_medication
        if not on_lipid_lowering_medication:
            comparison = "高於或等於" if ldl_is_eligible else "低於"
            lines.append(f"LDL-C {comparison}起始藥物治療血脂值（{patient.ldl_c:g} / {ldl_threshold:g}）")
        if ldl_is_eligible and not on_lipid_lowering_medication:
            if risk_category in {"extreme", "very_high", "high"}:
                lines.append("非藥物治療：生活型態改變與藥物治療並行")
            else:
                lines.append("非藥物治療：給藥前應有 3-6 個月生活型態改變，並處置心血管風險因子")

        show_targets_and_treatment = ldl_is_eligible or on_lipid_lowering_medication
        if show_targets_and_treatment:
            ldl_target = f"LDL-C < {ldl_threshold:g}"
            if on_statin_medication:
                ldl_status = "已達標" if patient.ldl_c is not None and patient.ldl_c < ldl_threshold else "未達標"
                ldl_target = f"{ldl_target} ({ldl_status})"
            targets = [ldl_target]
            if outcome.non_hdl_target is not None:
                non_hdl_target = f"non-HDL-C < {outcome.non_hdl_target:g}"
                non_hdl_value = patient.non_hdl_c()
                if on_statin_medication:
                    if non_hdl_value is not None:
                        non_hdl_status = "已達標" if non_hdl_value < outcome.non_hdl_target else "未達標"
                        non_hdl_target = f"{non_hdl_target} ({non_hdl_status})"
                    else:
                        missing_lipids = []
                        if patient.total_cholesterol is None:
                            missing_lipids.append("TC")
                        if patient.hdl_c is None:
                            missing_lipids.append("HDL")
                        non_hdl_target = f"{non_hdl_target} (缺 {', '.join(missing_lipids)})"
                targets.append(non_hdl_target)
            lines.append(f"主要/次要血脂目標值：{' / '.join(targets)}")

        if show_targets_and_treatment:
            lines.append(OUTPUT_DIVIDER)
            configured_medications = self.medication_catalog.selected(self.hospital_medication_codes) if self is not None else []
            medication_lines = medication_output_lines(configured_medications)
            if medication_lines:
                lines.extend(medication_lines)
            elif self is not None and self.medication_settings_error is not None:
                lines.append(self.medication_settings_error)
            elif configured_medications:
                lines.append("院內新制可用藥物：已設定品項尚未到給付生效日")
            else:
                lines.append("院內新制可用藥物：尚未設定")
            if on_statin_medication and patient.ldl_c is not None and patient.ldl_c >= ldl_threshold:
                lines.append("若追蹤治療調藥仍未達標，可考慮申請 PCSK9 單株抗體 (Evolocumab, Alirocumab)，或自費 siRNA、ATP citrate lyase 抑制劑 (Inclisiran, Bempedoic acid)。")
            if risk_category in {"extreme", "very_high", "high"}:
                lines.append("追蹤時程：起始治療 6-8 週後、穩定期每 6 個月、改藥後 1-3 個月內")
            elif risk_category in {"moderate", "low"}:
                lines.append("追蹤時程：起始治療 6-8 週後、穩定期每 6-12 個月")
        return lines


def run() -> None:
    root = ctk.CTk()
    App(root)
    root.mainloop()
