# 新制降膽固醇藥物健保給付助理

<img src="assets/statin_nhi.png" alt="深藍心臟與青綠藥丸圖示" width="112">

Windows 桌面工具，協助醫療人員整理資料、確認 ASCVD 風險分級與血脂目標，並顯示院內已設定且已達生效日的新制藥物清單。提供繁體中文介面，以 Python／CustomTkinter 開發。

程式版本：**v1.2.3**。本儲存庫為獨立專案，非健保署官方軟體，亦不代表任何醫院或機關的審核或背書。

## 下載與開始使用

1. 從 [GitHub Releases](https://github.com/ccwang11/Statin_NHI_TW/releases) 下載 `Statin_NHI.exe`，放入可寫入的個人資料夾。
2. 執行程式，輸入資料或貼上適合在本機處理的病歷內容。
3. 逐項確認擷取結果，修正否定、家族史、時態及缺漏資料，再按「判定」。
4. 在「藥品」設定院內可開立品項的健保代碼；主檔不代表任一醫院的實際庫存。
5. 「複製摘要」只複製分隔線前的判讀與 FH 結果，不含分隔線後的藥物清單及追蹤提示。

EXE 尚未數位簽章，Windows 可能顯示未知發行者或 SmartScreen 提示。請依機構政策評估；SHA256 可比對下載檔案是否一致，不能證明軟體安全或發行者身分。PowerShell 查核方式：

```powershell
Get-FileHash .\Statin_NHI.exe -Algorithm SHA256
```

請與同一 Release 的 `SHA256SUMS.txt` 比對。更新 EXE 時保留自己的設定檔；發布包不提供任何院內預設品項。

## 功能與限制

- 手動表單、病歷文字半自動擷取、人工確認與輸出。
- ASCVD 風險分級、LDL-C／non-HDL-C 目標及追蹤提示。
- 慢性腎臟病的兩筆 eGFR／UACR 證據，以及符合條件時的 creatinine 推算。
- Taiwan FH criteria 輔助篩檢。
- 院內藥品設定、生效日篩選與公告更新提醒。

程式未完整驗證個別藥品的前置療程、生活型態介入、事前審查、續用資格及全部給付條件。達到 LDL 門檻、列出藥品或測試通過，不等於個案符合健保給付，也不等於臨床有效性或法規核准。最終仍須依官方現行規定、病歷證據與院內流程確認。完整實作邊界見 [規則與限制](docs/RULES.md)。

## 規定版本與生效日

規則來源包括 2026/9/1 生效的給付規定，以及 2026/10/29「健保審字第1150672925號」公告（2026/12/1 生效，涉及 2.6.1、2.6.3）。此公告不是整套風險判讀與 FH 篩檢的唯一依據。

CSV 共 63 項：原有 57 項自 `2026-09-01`、新增 6 項自 `2026-12-01` 納入清單。`effective_date` 是納入本程式新制清單的日期，非首次取得健保給付日期。程式依台灣當日日期篩選；未生效品項可先儲存，重新判讀時再決定是否輸出。

本程式不會連線下載健保公告，也不會自行更新 CSV 或規則。任何個人設定的外部定期搜尋任務不屬於此專案功能。官方來源、附件雜湊與更新程序見 [資料來源](docs/REFERENCES.md)。

## 設定與隱私

`Statin_NHI_available.json` 儲存院內藥品及公告提醒偏好。原始碼執行時位於專案根目錄；EXE 執行時位於 EXE 同資料夾。可由程式建立，也可複製 [空白範例](examples/Statin_NHI_available.example.json) 並重新命名。請不要直接覆蓋已使用的設定。

病歷文字與病人表單資料不會由本程式自動寫入檔案或上傳；複製摘要會寫入系統剪貼簿。意見回饋連結會開啟外部網站。請勿在 Issue、Pull Request、回饋表單、截圖或 CI 產物上傳真實病人資料。詳見 [隱私與設定](docs/PRIVACY.md)。

## 從原始碼執行

本倉庫為乾淨的首次公開快照，不含先前私有 Git 歷史。需 Python 3.13 與可用的 Tcl/Tk。Windows 建議使用 python.org 安裝程式並安裝 Tcl/Tk：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

亦可在建立環境後執行 `run.cmd`。不要從其他電腦複製 `.venv` 或捆入另一套 Tcl/Tk 腳本。

開發測試與打包：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --distpath build/verification-dist --workpath build/verification-work Statin_NHI.spec
```

測試使用人工編造資料。Linux 可執行規則測試；GUI 需顯示環境，Windows EXE 必須在 Windows 打包。重建步驟與 Actions 流程見 [開發與發布](docs/DEVELOPMENT.md)。

## 文件

| 文件 | 內容 |
| --- | --- |
| [架構](docs/ARCHITECTURE.md) | 模組、資料流及設定邊界 |
| [規則與限制](docs/RULES.md) | 現行判讀、parser 證據與未實作部分 |
| [資料來源](docs/REFERENCES.md) | 官方規定、日期、附件及更新程序 |
| [隱私與設定](docs/PRIVACY.md) | 資料處理、設定格式與舊檔遷移 |
| [開發與發布](docs/DEVELOPMENT.md) | 安裝、測試、GUI 驗證、Windows 打包 |
| [貢獻指南](CONTRIBUTING.md) | 回報問題與提交修改 |
| [安全回報](SECURITY.md) | 私密回報方式及資料保護 |
| [第三方聲明](THIRD_PARTY_NOTICES.md) | 相依套件、參考資料與圖示來源 |
| [公開版來源](docs/PROVENANCE.md) | 首次公開快照、授權與測試資料來源 |
| [更新紀錄](CHANGELOG.md) | 已發布版本及尚未發布修改 |

## 授權

本專案自有原始碼與文件採 [MIT License](LICENSE)，允許修改、散布及商用，須保留著作權與授權聲明。第三方程式、文件及官方附件依原權利人條款，不因放在此倉庫就改為 MIT。請參閱 [第三方聲明](THIRD_PARTY_NOTICES.md)。
