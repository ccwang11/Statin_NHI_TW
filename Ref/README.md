# 參考資料

本目錄提供程式使用的 CSV 及官方公告快照，不包含任何院內實際可開立設定。來源、日期、授權及核對限制見 [資料來源](../docs/REFERENCES.md)與 [第三方聲明](../THIRD_PARTY_NOTICES.md)。

- CSV 有 63 項，`effective_date` 控制納入本程式新制清單的日期。
- PDF 是歷史快照，不能直接當成今日完整規定。
- `manifest.json` 記錄附件雜湊、官方公告及下載網址；三份 PDF 均已重新下載並確認雜湊一致。`verified_on` 記錄核對日期，原始取得時間未知的 `downloaded_at` 保留 `null`。
- 個別院所使用的 `Statin_NHI_available.json` 不應放入本目錄或提交 Git。
