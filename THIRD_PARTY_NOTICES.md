# 第三方資料與授權

## 自有程式與文件

本專案自有程式、維護文件及人工測試採根目錄 MIT License。MIT 不變更第三方材料、商標、官方標誌或文件的原授權，也不表示任何機關背書。

## 健保署資料

來源：衛生福利部中央健康保險署。`Ref/` 的官方 PDF 保留原文件，CSV 為專案依給付資料整理的選用主檔，並非完整即時藥品資料庫。引用與修改位置見 [資料來源](docs/REFERENCES.md)。

健保署[政府網站資料開放宣告](https://www.nhi.gov.tw/ch/cp-4379-5d212-3280-1.html) 要求標示來源，另有個資、商標及特別聲明第三方著作等例外；本專案未將官方附件另行宣稱為 MIT。原文優先，請自行確認特定資料的適用條款。

## 文獻

Li Y-H et al., *2017 Taiwan lipid guidelines for high risk patients*, Journal of the Formosan Medical Association 116 (2017), 217–248. DOI: [10.1016/j.jfma.2016.11.013](https://doi.org/10.1016/j.jfma.2016.11.013)。原文標示 CC BY-NC-ND 4.0，著作權為 Formosan Medical Association，由 Elsevier Taiwan LLC 發布。本公開版不再追蹤該 PDF 全文，以書目與 DOI 提供查閱；該文及其圖表未改為 MIT。FH 評分相關臨床資料須核對原文、官方規定及其各自權利。

## 相依程式

以下是主要相依元件，實際版本見 requirements 與 Actions 安裝紀錄；轉散布須保留其適用授權。此清單不把第三方原始碼重授權為 MIT。

| 元件 | 用途 | 上游授權／說明 |
| --- | --- | --- |
| [Python](https://docs.python.org/3/license.html) | 執行環境／標準函式庫 | PSF 及文件列出的第三方聲明 |
| [Tcl/Tk](https://www.tcl-lang.org/software/tcltk/license.html) | GUI runtime | 上游寬鬆授權；由 Python／PyInstaller 提供 |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter/blob/master/LICENSE) | GUI 元件與資源 | MIT；套件附帶字型亦須依其個別聲明 |
| [darkdetect](https://github.com/albertosottile/darkdetect/blob/master/LICENSE) | 外觀偵測 | BSD-3-Clause |
| [packaging](https://github.com/pypa/packaging) | 套件版本處理 | Apache-2.0／BSD-2-Clause |
| [Pillow](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | 驗證截圖及圖示轉檔 | 套件所附 HPND 及第三方聲明 |
| [PyInstaller](https://pyinstaller.org/en/stable/license.html) | Windows 打包 | GPL-2.0-or-later 加 bootloader exception；不把自有應用程式強制改為 GPL |

GitHub Actions 工具依各 actions 儲存庫授權；不是應用程式的臨床規則來源。

## 圖示

`assets/statin_nhi.png` 為本專案透過 OpenAI 圖像生成工具產生、由維護者選定的深藍心臟與青綠／白色藥丸設計；ICO 由此圖轉換。維護者以可授權的權利範圍納入 MIT，無宣稱生成圖像具排他權，亦非健保署或醫院標誌。
