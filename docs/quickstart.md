# 快速开始

## 环境准备

```bash
conda env create -f environment.yml   # 首次安装依赖
conda activate sectorbreaker           # 激活 conda 环境
cd frontend && npm install             # 首次安装前端依赖
```

## 启动项目

需要两个终端窗口。先激活 conda 环境再启动服务，`Ctrl+C` 随时停掉对应服务。

**终端 1 — 后端**（端口 8030）：

```bash
conda activate sectorbreaker
python -m uvicorn backend.app.api.app:app --port 8030 --reload
```

**终端 2 — 前端**（端口 5173）：

```bash
conda activate sectorbreaker
cd frontend
npm run dev
```

打开浏览器访问 `http://127.0.0.1:5173/`。

## 使用流程

1. 在首页输入你想了解的领域（例如"AI Agent 工具"）
2. 点击"开始破壁"
3. 观察流程图逐步推进，日志面板显示实时进度
4. 研究完成后进入审查页面，可以补充自己的信息
5. 确认继续，查看最终产物
6. 可以基于研究结果继续追问，或导出为 Obsidian 知识库

## LLM 配置

点击右下角"LLM 设置"，填入：

- **Base URL**：OpenAI 兼容的 API 地址
- **API Key**：你的密钥
- **Model**：模型名称

支持任何 OpenAI 兼容的 API（OpenAI、DeepSeek、Moonshot、本地 Ollama 等）。

## 测试

```bash
# 后端测试
conda activate sectorbreaker
python -m pytest -q

# 前端测试
cd frontend
npm test

# 前端构建
cd frontend
npm run build
```
