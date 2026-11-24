#!/usr/bin/env bash
# 重新生成 frontend/lib/novel.js（浏览器版排版算法 + 作者识别）
set -e
cd "$(dirname "$0")/.."
npx --yes esbuild scripts/browser_entry.mjs \
  --bundle --format=iife --global-name=NovelFmt --target=es2019 \
  --outfile=frontend/lib/novel.js
npx --yes esbuild scripts/worker_entry.mjs \
  --bundle --format=iife --target=es2019 \
  --outfile=frontend/lib/novel-worker.js
