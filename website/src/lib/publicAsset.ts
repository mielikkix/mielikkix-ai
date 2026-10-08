// Versioned URL for a file in public/, e.g. "/widget-common.js?v=3f9a1c2b".
//
// The plain public/*.js scripts keep the same URL on every deploy, and
// Hostinger serves them with a 7-day Cache-Control. After a deploy a returning
// visitor could run a new demo script against last week's widget-common.js:
// "lang is not a function" and a dead demo (QA 2026-10-08, W-01), and a
// stale i18n-guard.js showed English URLs in Norwegian (W-02). The query
// string is a hash of the file's content, so it only changes when the file
// does, and an unchanged file stays cached.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const cache = new Map<string, string>();

// The build and dev server normally run from website/; also allow the repo root.
const PUBLIC_DIR = [path.join(process.cwd(), "public"), path.join(process.cwd(), "website", "public")].find(existsSync)
  ?? path.join(process.cwd(), "public");

export function publicAsset(urlPath: string): string {
  let url = cache.get(urlPath);
  if (!url) {
    const file = path.join(PUBLIC_DIR, ...urlPath.split("/").filter(Boolean));
    const hash = createHash("sha256").update(readFileSync(file)).digest("hex").slice(0, 10);
    url = `${urlPath}?v=${hash}`;
    cache.set(urlPath, url);
  }
  return url;
}
