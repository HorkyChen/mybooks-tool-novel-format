# mybooks-tool-novel-format

MyBooks「工具箱」里的小说排版整理工具。界面按图书管理的习惯做：搜索、分页、跨页勾选，
点「开始排版」后弹出与原版一致的排版弹窗，逐本处理并覆盖回书库。

**排版与写回都复用主程序的 `/api/novel_format/*` 接口（JSON）**，本工具不额外落库、
不改后端协议，只负责界面与交互。

## 功能

- 书籍列表：搜索（支持 calibre 语法）、分页（20/50/100/200）、封面/标签/格式展示
- 勾选：跨页保留、按 id 去重、全选本页、一键清空
- 弹窗：原文/结果只读预览（各限 5 万字）、排版选项、繁简转换、章节分割/重排、
  自动覆盖、自动识别作者、覆盖/跳过/完成、批次进度与日志
- 内存保护：每本之间停 200ms，每 10 本额外停 800ms，给浏览器 GC 回收大字符串
- 覆盖成功后由主程序追加「精校」标签（只追加，不清空原有标签）

## 依赖

- MyBooks v4.7.0+（Core API 1.5.0）
- 主程序需包含 `webserver/handlers/novel_format.py` 注册的接口：
  - `GET  /api/novel_format/<id>/text`
  - `POST /api/novel_format/<id>/save`
  - `POST /api/novel_format/convert`

## 目录

```
manifest.json
backend/tool.py              # BaseTool 入口（仅元信息，逻辑都在主程序）
frontend/index.html          # 书表 + 弹窗（原生 JS）
frontend/lib/novel.js        # 浏览器版排版算法（由 formatter_src 打包）
backend/formatter_src/       # 算法源码副本（novelUtils / textUtils / regex / authorDetect）
scripts/browser_entry.mjs    # 打包入口
scripts/build-browser.sh     # 重新生成 frontend/lib/novel.js
```

## 开发 / 打包

```bash
bash scripts/build-browser.sh     # 改了算法后重新打包
npm install -g mybooks-tools-builder
mytool validate .
mytool build                      # dist/novel_format-<version>.zip
```

## 安装

1. 系统设置 → 高级配置项 → 打开工具开发者模式
2. 系统管理 → 工具箱 → 上传 zip
3. 重启 MyBooks 服务
