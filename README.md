# mybooks-tool-novel-format

MyBooks「工具箱」里的小说排版整理工具。把 TXT 小说按段落/章节重新排版后覆盖回书库，
可选追加「精校」标签。**正文的读取和写回都在服务端完成**，浏览器只负责选书和看进度，
因此百万字长篇也不会把标签页撑到 Out of Memory。

## 功能

- 搜索书库、勾选多本（只列出有 TXT 的书）
- 段落排版：智能换行、段首缩进、长段落拆分、清理首尾空格
- 章节处理：章节标题分行、合并重复章节标题、去除重复行、去掉行尾数字
- 覆盖原 TXT（保持原文件编码：UTF-8 / GB18030 / Big5）
- 可选追加「精校」标签（只追加，不动原有标签）
- 后台任务 + 进度条 + 日志，可中途取消

## 实现方式

```
frontend/         iframe 页面（原生 JS + 脚手架 theme.css）
backend/tool.py   BaseTool + api_routes（search / start / status / cancel）
backend/formatter.js  排版算法（由 app/src/utils/novel 打包成的 Node CLI，随包携带）
backend/formatter_src/  算法源码副本（novelUtils / textUtils / regex）
scripts/formatter_entry.mjs / build-formatter.sh  重新打包 formatter.js
```

每本书的处理流程：

1. `api.calibre.get_metadata()` 取书名
2. `api.calibre.format_abspath(book_id, "TXT")` 拿真实路径
3. 读文件 → 探测编码 → 转成 UTF-8 临时文件
4. `node formatter.js in.txt out.txt opts.json`（每本一个子进程，退出即释放内存）
5. 按原编码写回临时文件 → `api.calibre.add_format(..., replace=True)`
6. 可选 `api.calibre.set_metadata()` 追加「精校」标签

## 开发

```bash
npm install -g mybooks-tools-builder
mytool validate .
mytool build          # 产出 dist/novel_format-<version>.zip
```

重新生成 `backend/formatter.js`（改了排版算法后）：

```bash
bash scripts/build-formatter.sh
```

## 安装到 MyBooks

1. 系统设置 → 高级配置项 → 打开工具开发者模式
2. 系统管理 → 工具箱 → 上传 `dist/novel_format-0.1.0.zip`
3. 重启 MyBooks 服务

## 要求

- MyBooks v4.7.0+（Core API 1.5.0）
- 运行容器内需要 `node`（官方镜像自带 Node 22）
