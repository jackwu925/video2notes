# Video2Notes

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) | 简体中文

![Video2Notes cover](assets/cover.png)

## Overview

Video2Notes 可以把长视频转成易读的笔记。它支持下载或导入媒体文件，使用 Whisper 进行语音转写，并通过 OpenAI 兼容的大模型 API 生成 Markdown 分析报告。

本项目面向本地工作流设计：在仓库根目录启动网页 UI，生成的文件统一保存在 `data/` 下，并在重复分析同一视频时复用已生成的音频、字幕和总结。

## Feature

- 使用 `video2notes-ui` 启动本地 Streamlit 网页 UI
- 支持 Bilibili、YouTube 以及其他 `yt-dlp` 支持的视频来源
- 支持浏览器导出的 `cookies.txt`，用于需要登录态的网站
- 支持导入本地音频或视频文件，跳过在线下载
- 使用 Whisper 转写语音，支持 `auto`、`cpu` 和 `cuda` 设备模式
- 默认生成带时间戳的 `srt` 字幕
- 使用 OpenAI 兼容的大模型 API 生成中文或英文笔记
- 内置 OpenAI、SiliconFlow、DeepSeek、Qwen、OpenRouter、Ollama 和 LM Studio 供应商预设
- 支持从粘贴链接或相对路径 URL 文件批量处理视频
- 使用相对路径保存产物：`data/audio`、`data/subtitles`、`data/summaries`、`data/metadata`
- 支持在网页 UI 中下载 Markdown 报告

## Installation

克隆仓库并创建 conda 环境：

```bash
git clone https://github.com/jackwu925/video2notes.git
cd video2notes
conda create -n video2notes python=3.10 -y
conda activate video2notes
conda install -c conda-forge ffmpeg -y
python -m pip install -U pip
```

安装 Video2Notes 依赖前，请先安装 PyTorch。请根据你的操作系统、包管理器、CUDA 版本和 GPU 驱动，在 PyTorch 官方安装选择器中选择对应命令：

```text
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

安装 PyTorch 后，安装 Video2Notes 及其锁定的运行依赖：

```bash
python -m pip install -r requirements.txt
```

所有命令都应在项目根目录执行。`requirements.txt` 会安装当前本地仓库，因此激活 conda 环境后可以直接启动网页 UI：

```bash
video2notes-ui
```

打开终端中输出的 Streamlit 地址，在 `API Configuration` 中配置供应商，粘贴视频链接，然后点击 `Run`。

如果只使用命令行，不安装网页 UI：

```bash
python -m pip install -e .
video2notes run "VIDEO_URL" --reuse-existing
```

分析 Bilibili 视频前，请先导出自己的浏览器 cookies。在 Chrome 中使用 `Get cookies.txt LOCALLY` 插件，把 cookies 保存为相对路径文件，例如 `cookies.txt`，然后在网页 UI 的 `cookies.txt` 输入框中填写该文件。Cookie 文件和生成的数据都会被 git 忽略。

只生成字幕：

```bash
video2notes run "VIDEO_URL" --skip-llm
```

使用本地媒体文件，跳过下载：

```bash
video2notes run --media-file data/imports/demo.mp4 --reuse-existing
```

从相对路径文件批量处理多个链接：

```bash
video2notes run --url-file data/urls.txt --reuse-existing
```

命令行的大模型配置可以写入本地 `.env` 文件。请在项目根目录手动创建 `.env`，并填写你的 OpenAI 兼容供应商配置：

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=60
```

## License

Video2Notes 基于 [MIT License](LICENSE) 发布。
