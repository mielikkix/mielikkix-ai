// Run: npm test  (node --test, Node 22+ strips the TypeScript types itself)
import { test } from "node:test";
import assert from "node:assert/strict";
import { styleBareTables } from "../src/lib/articleTables.ts";

const bare = "<p>Intro</p>\n<table>\n<thead>\n<tr>\n<th>Area</th>\n</tr>\n</thead>\n<tbody>\n<tr>\n<td>Name</td>\n</tr>\n</tbody>\n</table>\n<p>After</p>";

test("a bare table is wrapped and every header and data cell is styled", () => {
  const out = styleBareTables(bare);
  assert.match(out, /<div class="overflow-x-auto rounded-2xl border border-slate-200"><table class="[^"]+">/);
  assert.match(out, /<\/table><\/div>\n<p>After<\/p>$/);
  assert.match(out, /<th class="bg-slate-50 px-4 py-2 font-semibold">Area<\/th>/);
  assert.match(out, /<td class="border-t border-slate-200 px-4 py-2 align-top">Name<\/td>/);
  assert.doesNotMatch(out, /<t[hd]>/);
});

test("text outside and inside the table is unchanged", () => {
  const strip = (s: string) => s.replace(/<[^>]+>/g, "");
  assert.equal(strip(styleBareTables(bare)), strip(bare));
});

test("a table that already has classes is left exactly as authored", () => {
  const styled = '<div class="overflow-hidden rounded-2xl"><table class="w-full"><tbody><tr><td class="px-4">x</td></tr></tbody></table></div>';
  assert.equal(styleBareTables(styled), styled);
});

test("several bare tables are each wrapped once", () => {
  const out = styleBareTables(`${bare}${bare}`);
  assert.equal(out.match(/<div class="overflow-x-auto/g)?.length, 2);
  assert.equal(out.match(/<\/table><\/div>/g)?.length, 2);
});

test("content without tables is returned unchanged", () => {
  assert.equal(styleBareTables("<p>No tables here.</p>"), "<p>No tables here.</p>");
});
