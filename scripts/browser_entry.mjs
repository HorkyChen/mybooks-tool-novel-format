// 浏览器端打包入口：把排版算法和作者识别挂到 window.NovelFmt
import { formatNovelText, splitInlineChapterTitles, reorderChaptersByTitle } from "../backend/formatter_src/novelUtils.js";
import { detectAuthor } from "../backend/formatter_src/authorDetect.js";

export { formatNovelText, splitInlineChapterTitles, reorderChaptersByTitle, detectAuthor };
