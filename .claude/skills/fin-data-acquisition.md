# fin-data-acquisition — 经济金融数据获取与实证脚本生成

> **注意**：本文件是文档版本。操作版本见 `.cursor/skills/fin-data-acquisition/SKILL.md`。

## 功能

根据研究设计自动获取数据，验证质量，并生成可直接运行的回归分析脚本。

## 【强制】数据源预检查（第一步必须执行）

在任何数据获取代码运行之前，**必须**先执行以下检查。

### 禁止静默fallback

- ❌ **禁止**在用户未授权的情况下自动使用模拟数据
- ❌ **禁止**跳过数据源检查直接运行实证脚本
- ❌ **禁止**在正文中写入模拟数据的回归系数和统计量
- ✅ 模拟数据仅在用户明确授权后才可使用

### 核心模块

```python
from scripts.data_source_checker import (
    DataSourceChecker, DataRequirement, check_and_confirm
)
from scripts.pipeline_checkpoint import InteractivePipelineCheckpoint

# 第1步：定义本研究需要的数据
requirements = [
    DataRequirement(
        name="financial_data",
        user_facing_name="A股财务数据",
        description="资产负债率、ROA、规模等财务指标",
        sources=["tushare", "wind", "csmar", "akshare"],
        required=True,
    ),
]

# 第2步：执行数据源检查
result = check_and_confirm(requirements)

# 第3步：硬中断——如果需要模拟数据，必须授权
if result.requires_synthetic_data:
    cp = InteractivePipelineCheckpoint()
    authorized = cp.authorize_synthetic_or_stop(purpose="本研究所需的数据")
    if not authorized:
        print("流程暂停。请获取真实数据后重启，或更换研究方向。")
        sys.exit(0)
```

## 详见

完整操作文档：`.cursor/skills/fin-data-acquisition/SKILL.md`
