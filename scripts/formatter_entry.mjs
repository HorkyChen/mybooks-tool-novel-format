// 命令行入口：node formatter.js <input.txt> <output.txt> <options.json>
// 由 scripts/build-formatter.sh 用 esbuild 打包成 backend/formatter.js
import fs from "node:fs";
import { formatNovelText } from "../backend/formatter_src/novelUtils.js";

const [input, output, optsPath] = process.argv.slice(2);
if (!input || !output) {
    console.error("usage: node formatter.js <input.txt> <output.txt> [options.json]");
    process.exit(2);
}
const opts = optsPath && fs.existsSync(optsPath) ? JSON.parse(fs.readFileSync(optsPath, "utf8")) : {};
const text = fs.readFileSync(input, "utf8");
(async () => {
    const result = await formatNovelText(text, opts);
    fs.writeFileSync(output, result, "utf8");
})().catch((err) => {
    console.error(String(err && err.stack || err));
    process.exit(1);
});
