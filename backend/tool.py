"""小说排版整理 —— MyBooks Toolbox 工具后端入口。

排版与覆盖动作全部复用主程序的 `/api/novel_format/*` 接口（JSON 请求/响应），
工具本身只负责选书界面和弹窗交互，因此这里的 BaseTool 只保留工具元信息。
"""
from webserver.toolbox.base_tool import BaseTool

TOOL_ID = "novel_format"


class NovelFormat(BaseTool):
    service_item_name = "小说排版整理"

    @staticmethod
    def info():
        return {
            "tool_id": TOOL_ID,
            "name": "小说排版整理",
            "description": "批量把 TXT 小说按段落/章节重新排版并覆盖回书库，可选追加「精校」标签",
            "revision": "0.2.2",
            "author": "unlimited996",
            "repo_url": "https://github.com/unlimited996/mybooks-tool-novel-format",
        } 
