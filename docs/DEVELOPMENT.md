# 開發、驗證與發布

## 安裝

使用 Python 3.13，建立每台電腦自己的虛擬環境。Windows 須有 tkinter／Tcl/Tk；Linux 可跑測試，但開啟 GUI 另需顯示環境與系統 Tk。不要拷貝其他安裝位置的 `.venv`、Tcl/Tk 或私人的雲端環境設定。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py
```

Linux 對應指令為 `python3.13 -m venv .venv`、`.venv/bin/python -m pip install -r requirements-dev.txt`。Tcl/Tk 應由目前 Python 安裝或 PyInstaller hook 提供；倉庫不散布完整 Tcl/Tk runtime。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m statin_nhi.smoke build/reports/source.json
```

GUI 冒煙測試需可用桌面，使用臨時目錄中的人工設定，開啟主畫面、藥物日期欄與提醒視窗，核對提醒抑制、設定持久化及基本視窗邊界，輸出 JSON 與截圖。它不覆蓋每個欄位、每種 DPI 或完整臨床情境。關於、FH 與實際院內顯示仍需人工確認。

另以人工資料驗證單次異常 eGFR 的暫定分級及複製摘要提醒、無效 LDL-C 停止判讀並清除舊結果，最後輸出 `*-example.png` 主畫面截圖。README 的 `assets/app-example.png` 為人工範例截圖；更新時須確認不含真實病歷或院內設定，並註明實際截圖平台。

所有測試輸入均為人工編造。規則修改須新增能代表臨床邊界或排除條件的案例；請勿為了符合新實作而直接更改既有預期值，先核對來源。

## Windows 打包

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --distpath build/verification-dist --workpath build/verification-work Statin_NHI.spec
```

`Statin_NHI.spec` 內嵌程式、CustomTkinter 資源、CSV 與圖示；PyInstaller hook 收集目前 Python 的 Tcl/Tk。不打包個人或院內 JSON。Linux 產物不能當 Windows EXE。EXE 可接受 `--smoke-test <report-path>` 執行同一組 GUI 驗證，不是一般使用者的啟動參數。

## GitHub Actions

`Windows build` 由 main push、PR、手動觸發及 `v*` 標籤啟動：

1. 安裝依賴並檢查公開倉庫檔案規則。
2. 執行單元測試與原始碼 GUI 冒煙測試。
3. 打包至 `build/verification-dist`，再執行 EXE GUI 冒煙測試。
4. 上傳 Windows 產物、SHA256、說明與授權，以及 GUI 報告／截圖；Release 另提供含文件、來源快照與空白設定範例的 ZIP。
5. 僅版本標籤通過 build 後，由獨立 job 取得 `contents: write` 發布 Release。

一般 build 僅 `contents: read`，不使用院內設定或簽章金鑰。PR 執行不取得發布權限；不要改成會對不可信 PR 執行程式的 `pull_request_target` 流程。

Artifacts 是特定 commit 的建置結果；Release 才是版本發布入口。EXE 未簽章。授權與第三方聲明隨新版產物散布；較早 Release 的附件不會因後續提交而自動更新。

## 發版

- 先修改版本 `statin_nhi/__init__.py`、README 與 CHANGELOG。
- 確認官方依據、生效日、測試及 GUI 行為；不要納入院內 JSON。
- 推送 main 並確認流程結果；版本標籤必須等於 `v` 加程式版本。
- 推送 `vX.Y.Z` 後，確認標籤流程和 Release 資產，不把 queued 當完成。
- 真實 Windows 電腦仍須確認字型、縮放、寫入權限、EXE 啟動及個人設定保留。

授權、資料來源及隱私規則同樣適用於發行附件、Actions 截圖及日誌。
