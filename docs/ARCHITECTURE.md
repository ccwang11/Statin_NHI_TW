# 架構與資料流

對應原始碼版本：v1.2.4；更新日期：2026-11-09。

## 模組

| 模組 | 責任 |
| --- | --- |
| `main.py` | 初始化可用的 Tcl/Tk 並啟動 GUI；`--smoke-test` 用於隔離驗證 |
| `statin_nhi/models.py` | `PatientData`、日期與衍生資料 |
| `statin_nhi/parser.py` | 從輸入文字提出欄位候選值與複核提示 |
| `statin_nhi/rules.py` | 風險分級、血脂目標與 CKD 證據判定 |
| `statin_nhi/fh.py` | 手動證據與 LDL-C 的 FH 評分 |
| `statin_nhi/medications.py` | CSV 載入、生效日、院內設定與公告提醒偏好 |
| `statin_nhi/ui.py` | 輸入、人工確認、彈出視窗、判讀與剪貼簿 |
| `statin_nhi/smoke.py` | 使用暫存設定的原始碼／EXE GUI 冒煙測試 |
| `Ref/` | 程式主檔及官方規定附件快照 |

## 一次判讀

```mermaid
flowchart LR
    A[輸入文字或表單] --> B[parser 候選欄位]
    B --> C[使用者確認與修正]
    C --> V{數值與血壓格式有效}
    V -->|是| D[PatientData]
    V -->|否| X[清除舊結果並提示欄位錯誤]
    D --> E[規則與 FH 評分]
    F[CSV 藥物主檔] --> G[院內代碼交集與日期篩選]
    H[本機 JSON] --> G
    E --> R[分級、待補欄位與規則提醒]
    R --> I[結果畫面]
    G --> I
    I --> J[使用者複製摘要]
```

parser 結果不能視為確診。`evaluate_all()` 現在僅回傳新制規則結果；舊設計草稿的 TG／舊制輸出未啟用。藥物清單只與院內設定及日期比對，不是完整個別用藥給付引擎。

### 輸入驗證與複核狀態

`ui.py` 的 `parse_nonnegative_number()` 只接受空白或有限且不小於零的數字。動態欄位更新將無效數值視為缺漏，避免輸入過程中拋出錯誤；按「判定」時，`build_patient_data()` 先呼叫 `_validate_numeric_inputs()`，逐項核對 `NUMERIC_LABELS` 所列欄位及血壓格式。驗證失敗會在 `evaluate_patient()` 顯示錯誤並清除舊結果，不進入規則判讀。這不驗證完整生理範圍或資料單位。

`RuleOutcome.status` 為 `needs_review` 時，結果分級加註「暫定分級，需人工複核」。`missing_fields` 與 `follow_up_notes` 一律顯示在 `OUTPUT_DIVIDER` 之前；`copy_result_summary()` 因此保留待補資料與判讀提醒。分隔線後的院內藥品及追蹤時程不複製。風險分級及給付門檻仍由 `rules.py` 負責。

## 檔案位置

原始碼執行以專案根目錄為設定位置；凍結 EXE 以執行檔所在資料夾為設定位置。CSV 與圖示由 PyInstaller 內嵌，使用 `_MEIPASS` 讀取；設定寫入位置不使用 `_MEIPASS`。

設定以 `.tmp` 寫入後替換原檔。格式錯誤時拒絕覆寫，避免藥物清單或提醒偏好遺失。此流程不是多程序同步鎖；請避免同時執行多個實例編輯同一個設定檔。

臨床輸入不會由應用程式自動保存。設定格式與舊提醒檔遷移詳見 [PRIVACY.md](PRIVACY.md)。
