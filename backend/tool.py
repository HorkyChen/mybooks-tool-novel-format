"""小说排版整理 —— MyBooks Toolbox 工具后端。

设计要点：
1. 正文读写全部在服务端完成：`api.calibre.format_abspath()` 拿到 TXT 路径，排版算法用
   随包携带的 Node 脚本（`backend/formatter.js`）执行，结果直接 `add_format()` 写回。
   浏览器只收进度，不再把几十 MB 正文塞进标签页，从根上避开前端的 OOM。
2. 每本书单独起一个 node 子进程，处理完自动退出，内存不会在批次之间累积。
3. 覆盖成功后可追加「精校」标签（只加不覆盖原有标签），方便下一批自动跳过。
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time

from webserver.handlers.base import BaseHandler, js, auth
from webserver.i18n import _
from webserver.services import AsyncService
from webserver.toolbox.base_tool import BaseTool

TOOL_ID = "novel_format"
REVISED_TAG = "精校"
MAX_TEXT_BYTES = 100 * 1024 * 1024
NODE_TIMEOUT = 600

_STATUS_LOCK = threading.Lock()


def _decode_text(raw):
    """返回 (text, encoding)。encoding 用于写回时保持原文件编码。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc), enc
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace"), "utf-8"


def _authors_text(value):
    if isinstance(value, (list, tuple, set)):
        return " / ".join(str(x) for x in value if x)
    return str(value or "")


def _empty_status():
    return {
        "status": "idle",
        "total": 0,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "current": "",
        "error": "",
        "cancel_requested": False,
        "started_at": None,
        "finished_at": None,
        "logs": [],
    }


class NovelFormat(BaseTool):
    service_item_name = "小说排版整理"

    @staticmethod
    def info():
        return {
            "tool_id": TOOL_ID,
            "name": "小说排版整理",
            "description": "批量把 TXT 小说按段落/章节重新排版并覆盖回书库，可选追加「精校」标签",
            "revision": "0.1.0",
            "author": "unlimited996",
            "repo_url": "https://github.com/unlimited996/mybooks-tool-novel-format",
        }

    # ------------------------------------------------------------------ 状态文件

    def _status_path(self):
        return os.path.join(self.api.storage.get_work_dir(), "status.json")

    def _read_status(self):
        try:
            with open(self._status_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else _empty_status()
        except (OSError, ValueError):
            return _empty_status()

    def _write_status(self, data):
        path = self._status_path()
        tmp = path + ".tmp"
        with _STATUS_LOCK:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)

    def _update(self, **kwargs):
        data = self._read_status()
        data.update(kwargs)
        self._write_status(data)
        return data

    def _log(self, message):
        data = self._read_status()
        logs = data.get("logs") or []
        logs.append("%s %s" % (time.strftime("%H:%M:%S"), message))
        data["logs"] = logs[-200:]
        self._write_status(data)

    # ------------------------------------------------------------------ 查询

    @AsyncService.register_function
    def search(self, query="", limit=50):
        query = (query or "").strip()
        limit = max(1, min(int(limit or 50), 200))
        if query:
            books = self.api.calibre.search_books(query, max_results=limit)
        else:
            ids = list(self.api.calibre.all_book_ids())[:limit]
            books = self.api.calibre.get_data_as_dict(ids) if ids else []
        items = []
        for book in books:
            formats = book.get("formats") or book.get("available_formats") or []
            items.append({
                "id": book.get("id"),
                "title": book.get("title") or "",
                "authors": _authors_text(book.get("authors")),
                "has_txt": "TXT" in [str(x).upper() for x in formats],
            })
        return {"items": items, "total": len(items)}

    @AsyncService.register_function
    def status(self):
        data = self._read_status()
        data.pop("cancel_requested", None)
        return data

    # ------------------------------------------------------------------ 任务

    @AsyncService.register_function
    def cancel(self):
        data = self._read_status()
        if data.get("status") != "running":
            raise RuntimeError(_("当前没有正在运行的任务"))
        data["cancel_requested"] = True
        self._write_status(data)
        return {"status": "cancelling"}

    @AsyncService.register_function
    def start(self, book_ids, options=None):
        book_ids = [int(x) for x in (book_ids or []) if str(x).isdigit()]
        if not book_ids:
            raise ValueError(_("请先选择要处理的书籍"))
        options = options if isinstance(options, dict) else {}

        current = self._read_status()
        if current.get("status") == "running":
            return current

        data = _empty_status()
        data.update({
            "status": "running",
            "total": len(book_ids),
            "started_at": time.time(),
        })
        self._write_status(data)

        task_id = self.api.tasks.create_task(progress_data={
            "total": len(book_ids), "processed": 0,
        })
        self._run(book_ids, options, task_id)
        return self.status()

    @AsyncService.register_service
    def _run(self, book_ids, options, task_id):
        total = len(book_ids)
        node = shutil.which("node") or "node"
        formatter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "formatter.js")
        add_tag = bool(options.get("add_tag", True))
        opts = {k: options.get(k) for k in (
            "enableChapterSplit", "filterText", "maxFilterLineLength",
            "enableLineEndNumbers", "enableParagraphSplit", "smartLineBreak",
            "enableTrim", "mergeDuplicateChapterTitles", "removeDuplicateLines",
            "enableIndent", "specialStart",
        ) if k in options}

        try:
            for index, book_id in enumerate(book_ids, start=1):
                if self._read_status().get("cancel_requested"):
                    self._update(status="cancelled", finished_at=time.time(), current="")
                    self._log("已取消")
                    self.api.tasks.complete_task(task_id, error_message="cancelled")
                    return

                title = ""
                work_dir = None
                try:
                    mi = self.api.calibre.get_metadata(book_id)
                    title = getattr(mi, "title", "") or str(book_id)
                    self._update(current=title)

                    path = self.api.calibre.format_abspath(book_id, "TXT")
                    if not path or not os.path.isfile(path):
                        raise RuntimeError(_("没有 TXT 格式"))
                    if os.path.getsize(path) > MAX_TEXT_BYTES:
                        raise RuntimeError(_("文件超过 %dMB") % (MAX_TEXT_BYTES // (1024 * 1024)))

                    with open(path, "rb") as f:
                        raw = f.read()
                    text, encoding = _decode_text(raw)

                    work_dir = self.api.storage.get_work_dir("book_%s" % book_id)
                    src = os.path.join(work_dir, "in.txt")
                    dst = os.path.join(work_dir, "out.txt")
                    opts_path = os.path.join(work_dir, "opts.json")
                    with open(src, "w", encoding="utf-8", newline="") as f:
                        f.write(text)
                    with open(opts_path, "w", encoding="utf-8") as f:
                        json.dump(opts, f, ensure_ascii=False)

                    proc = subprocess.run(
                        [node, formatter, src, dst, opts_path],
                        capture_output=True, timeout=NODE_TIMEOUT,
                    )
                    if proc.returncode != 0:
                        raise RuntimeError((proc.stderr or b"").decode("utf-8", "replace")[-300:] or "formatter failed")

                    with open(dst, "r", encoding="utf-8", newline="") as f:
                        formatted = f.read()

                    try:
                        payload = formatted.encode(encoding)
                    except (LookupError, UnicodeEncodeError):
                        encoding = "utf-8"
                        payload = formatted.encode("utf-8")

                    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="novel_format_tool_")
                    try:
                        with os.fdopen(fd, "wb") as f:
                            f.write(payload)
                        self.api.calibre.add_format(book_id, "TXT", tmp_path, replace=True)
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

                    if add_tag:
                        try:
                            tags = list(getattr(mi, "tags", []) or [])
                            if REVISED_TAG not in tags:
                                tags.append(REVISED_TAG)
                                mi.tags = tags
                                self.api.calibre.set_metadata(book_id, mi)
                        except Exception as err:
                            logging.warning("[novel_format] add tag failed for %s: %s", book_id, err)

                    stats = self._read_status()
                    self._update(
                        processed=index,
                        succeeded=stats.get("succeeded", 0) + 1,
                        current="",
                    )
                    self._log("%s 完成（%s）" % (title, encoding))

                except Exception as err:
                    stats = self._read_status()
                    self._update(
                        processed=index,
                        failed=stats.get("failed", 0) + 1,
                        current="",
                    )
                    self._log("%s 失败：%s" % (title or book_id, err))
                    logging.warning("[novel_format] book %s failed: %s", book_id, err)
                finally:
                    if work_dir:
                        try:
                            self.api.storage.cleanup_work_dir(work_dir)
                        except Exception:
                            pass

                percent = int(index * 100 / total) if total else 100
                self.api.tasks.update_progress(task_id, percent, progress_data={
                    "processed": index, "total": total,
                })

            final = self._read_status()
            self._update(status="done", finished_at=time.time(), current="")
            self.api.tasks.complete_task(task_id)
            self._log("全部结束：成功 %s，失败 %s" % (
                final.get("succeeded", 0), final.get("failed", 0)))
        except Exception as err:
            logging.exception("[novel_format] job failed")
            self._update(status="failed", error=str(err), finished_at=time.time())
            self.api.tasks.complete_task(task_id, error_message=str(err))


# ---------------------------------------------------------------------------
# HTTP handlers（manifest.json 的 api_routes）


class SearchHandler(BaseHandler):
    @js
    @auth
    def get(self):
        query = self.get_argument("q", "")
        limit = self.get_argument("limit", "50")
        return {"err": "ok", "data": NovelFormat().search(query, limit)}


class StatusHandler(BaseHandler):
    @js
    @auth
    def get(self):
        return {"err": "ok", "data": NovelFormat().status()}


class StartHandler(BaseHandler):
    @js
    @auth
    def post(self):
        try:
            body = json.loads(self.request.body or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
            data = NovelFormat().start(body.get("book_ids"), body.get("options"))
        except ValueError as err:
            return {"err": "params.invalid", "msg": str(err)}
        return {"err": "ok", "data": data}


class CancelHandler(BaseHandler):
    @js
    @auth
    def post(self):
        try:
            data = NovelFormat().cancel()
        except RuntimeError as err:
            return {"err": "cancel.invalid", "msg": str(err)}
        return {"err": "ok", "data": data}
