# data/ 目录说明

本目录存放项目使用的外部数据文件，这些是用户提供的本地参考文件，非自动生成。

## 文件说明

| 文件 | 说明 |
|------|------|
| `national_province_data_2026.json` | 全国各省科技创新面板数据（含研发投入、专利产出等指标） |
| `msci_esg_ratings.json` | MSCI ESG评级数据 |
| `msci_esg_ratings_xu.json` | MSCI ESG评级数据（xu来源） |
| `msci_esg_ratings_cyh.json` | MSCI ESG评级数据（cyh来源） |
| `test_national.json` | 全国数据测试文件 |
| `charts/test_save_1.png` | 测试图表输出 |
| `finance/.gitkeep` | 金融数据目录占位文件 |
| `test_templates/` | 期刊模板测试文件 |
| `test_templates/经济研究.tex` | 《经济研究》格式模板 |
| `test_templates/金融研究.tex` | 《金融研究》格式模板 |
| `test_templates/管理世界.tex` | 《管理世界》格式模板 |

## 数据来源

- **省级科技创新数据**：`national_province_data_2026.json` 由马克数据网（https://www.macrodur.cn）获取
- **ESG评级数据**：`msci_esg_ratings*.json` 来自MSCI官方网站或第三方数据聚合
- **期刊模板**：`test_templates/` 中的模板文件参考各期刊官方格式要求

## 更新方式

1. **省级数据**：访问马克数据网重新下载最新数据，替换 `national_province_data_2026.json`
2. **ESG评级**：从MSCI官网或数据供应商获取最新评级数据
3. **模板文件**：参考各期刊官网最新投稿指南更新

## 注意事项

- 本目录已在 `.gitignore` 中忽略，敏感数据不会提交到版本库
- 数据文件较大时建议使用 Git LFS 或单独管理
- 使用数据前请验证数据时效性和完整性
