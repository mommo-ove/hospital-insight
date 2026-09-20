# 院数 · 科室经营数据助手

将中文问题转换为可验证的本地数据查询。React 网页提供问答、图表、Excel 导入、指标说明和来源追溯。

## 从 Git 克隆后一条命令启动（推荐）

先安装并启动 Docker Desktop（Linux 服务器可使用 Docker Engine + Compose），然后在克隆得到的项目目录运行：

```sh
docker compose up --build -d
```

打开 http://127.0.0.1:8000，首次启动自动导入仓库内的《院管数据.xlsx》，可直接查询。也可在“数据管理”上传同格式更新。首次需要联网下载镜像与依赖。无需单独安装 Python、Node.js 或准备模型密钥。模型默认使用离线演示模式，启用云端模型需额外配置 `.env`。

此命令部署到运行它的电脑，默认仅本机访问。当前单用户版本不包含公网登录与权限控制，公网部署需要另外配置。

## 快速运行（Windows）

需要 Python 3.12+、Node.js 20.19+ 或 22.12+；推荐安装 uv。根目录如有 `院管数据.xlsx` 会自动导入；没有时可启动后在页面上传。

```powershell
# 在克隆得到的项目根目录运行
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

首次启动会安装依赖、构建前端，并将 Excel 导入本地 SQLite。打开 **http://127.0.0.1:8000**。按 Ctrl+C 停止。

已经完成安装和构建后，可用 `powershell -ExecutionPolicy Bypass -File .\start.ps1 -SkipBuild` 快速启动。`-Port 8002` 可改端口，`-Install` 可按锁文件重新安装前端依赖。脚本中的执行策略仅对本次 PowerShell 进程生效。

默认是**明确标识的离线规则演示模式**，支持首页示例、常见中文表达和连续追问，不代表通用大模型理解能力。没有模型密钥也可演示导入、计算、图表及来源。

## 接入云端模型

将 `.env.example` 复制为 `.env`，在本机编辑：

```dotenv
LLM_MODE=cloud
LLM_BASE_URL=https://你的服务商地址/v1
LLM_MODEL=你的模型名称
LLM_API_KEY=你的密钥
LLM_TIMEOUT_SECONDS=30
```

服务商需支持 `POST /chat/completions`、`response_format=json_object` 及本项目发送的标准请求参数。保存后重启后端。不会因为模型失败而悄悄切回演示模式；界面会显示实际模式、模型和错误原因。

云端接收用户问题、必要的上一轮查询条件、字段说明、科室名称、数据时间范围和人工编写的意图示例。原始 Excel、经营金额记录、查询结果、来源快照、完整历史答案均不发送给模型。答案文字与图表由本地结果生成。用户自己在问题中输入的内容会随问题发送。

密钥不通过网页输入、不返回前端、不写入日志或版本库。

## 演示问题

- `2025年心内科总收入是多少？`
- `那儿科呢？`
- `2026年4月各科室收入从高到低排名`
- `2025年心内科每月收入走势，按万元展示`
- `2025年内科的医保占比是多少？`
- `2026年4月心内科收入环比`
- `2025年心内科花费多少钱？` → 选择“合计收入”
- `2025年心内科次均费用` → 补充“按月分别展示”

“今年、上个月”按当前真实日期解释。样本截至 2026-04，因此之后的月份会返回无数据。未给时间默认最新有数据月，并在答案中提示。演示数据的真实性未由项目独立验证。

## 数据与指标规则

- 第一版支持单工作表、原有 22 个表头的 `.xlsx`，列顺序可变；最大 10 MB、20000 条记录。只接受经过确认的数值，公式单元格需先转为值。
- 数据管理先预览再提交。“年月＋科室”相同且内容一致时跳过；数值变更必须明确确认覆盖。预览后其他导入已提交时，旧预览需重做。
- 金额按整数分保存，结果可显示元或万元。收入及人次可加总；不会将合计再与分项相加。
- 单行医保占比保留原值；汇总使用“医保金额之和÷收入之和”。分母为零显示不可计算。
- 床位数只允许同月跨科室汇总。床位使用率、平均住院天数、次均费用保留科室月度原值；趋势必须按科室和月份拆分。
- 次均费用业务定义待确认，不当作患者账单，不生成跨期平均。
- 不完整期间可展示已有数据并明确警示；同比、环比要求两个期间完整，增长率不对零基期计算。
- 查询来源按文件、工作表、原始行和单元格记录。历史问答保存当时的数据快照，后续覆盖不改变旧答案。

当前原表的 224 条记录覆盖 8 个科室、28 个月（2024-01 至 2026-04）。实际包含的科室会随导入更新；`内科`、`外科`、`妇产科`按科室类型筛选。

## 开发与测试

```powershell
uv sync --frozen
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 在另一个终端：
cd frontend
npm ci
npm run dev
```

开发前端地址 http://127.0.0.1:5173，`/api` 自动代理到后端。后端 API 文档在 http://127.0.0.1:8000/docs。

```powershell
# 后端与固定问答回归
.\.venv\Scripts\python.exe -m pytest -q
# 离线80题评测：独立从Excel计算标准答案
.\.venv\Scripts\python.exe -X utf8 -m eval.run --mode demo --output docs/evaluation-demo.json
# 配置真实模型后运行；会产生服务商调用费用
.\.venv\Scripts\python.exe -X utf8 -m eval.run --mode cloud --output docs/evaluation-cloud.json
# 前端类型检查与生产构建
cd frontend
npm run build
# 浏览器测试使用独立临时数据库
npm run test:e2e
```

评测共 80 条固定问题：50 条可回答、15 条需澄清、15 条无数据或越界。既核对意图，也核对实际结果；标准计算直接读取原 Excel，不调用被测查询引擎。评测日历固定为 2026-09-20，便于复现；实际应用使用当天日期。

离线演示通过率不代表真实模型通过率。真实模型验收需配置后运行 `--mode cloud`，以报告中保存的模型、时间和结果为准；可回答问题目标≥95%，越界问题不得编造结果。

## Docker

```powershell
docker compose up --build -d
docker compose logs -f
docker compose down
```

需要 Docker Desktop 已启动。服务仅映射到本机 127.0.0.1:8000。数据库保存在命名卷 `hospital-data`，首次自动导入镜像内的原始工作簿；镜像不包含 `.env`，无需挂载本机文件。`docker compose down` 保留数据库。不要同时让本地服务和容器占用同一个端口。

## 结构

```text
backend/       数据目录、导入、查询编译、模型适配、会话、API
frontend/      React、Ant Design、ECharts 页面及浏览器测试
tests/         数据、查询、边界、模型协议与问答回归
eval/          80题固定评测与独立标准答案计算
docs/          架构、演示、评测与验收记录
data/          本地数据库（自动创建，不入库）
```

详细说明见 `docs/architecture.md` 和 `docs/demo.md`。本项目为单用户本地作品；未实现医院生产环境的账号权限、HIS 对接、多表关联或临床决策。

## 参考项目

借鉴 [WrenAI](https://github.com/Canner/WrenAI) 的指标语义层、[SQLBot](https://github.com/dataease/SQLBot) 的术语及中文问数流程、[DB-GPT](https://github.com/eosphoros-ai/DB-GPT) 的模块拆分思路。业务代码独立实现，没有复制这些项目的应用或界面代码。
