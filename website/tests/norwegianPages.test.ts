// Run: npm test. The /no/ copies built by integrations/norwegian-pages.mjs
// (QA 2026-10-05, BUG-13).
import { test } from "node:test";
import assert from "node:assert/strict";
import { toNorwegian } from "../integrations/norwegian-pages.mjs";

const dict = {
  NAV: { AGENTS: "Agenter" },
  SEO: { TITLE: "Om oss", DESCRIPTION: "Beskrivelse & mer" },
  FORM: { PLACEHOLDER: "Skriv her" },
};
const opts = { dict, twins: new Set(["/", "/agents/"]), site: "https://mielikkix.ai", route: "/agents/" };

const page = `<!DOCTYPE html><html lang="en"><head>
<link rel="canonical" href="https://mielikkix.ai/agents/">
<title data-i18n-doc-title="SEO.TITLE">About · Mielikkix</title>
<meta name="description" content="English" data-i18n-meta-desc="SEO.DESCRIPTION">
<meta property="og:url" content="https://mielikkix.ai/agents/">
</head><body data-page="agents">
<a href="/agents/" data-i18n="NAV.AGENTS" class="x">Agents</a>
<a href="/blog/">Blog</a>
<a href="/pricing/#chat">Pricing</a>
<a href="https://app.mielikkix.ai/register">Sign up</a>
<input placeholder="Type here" data-i18n-attr="placeholder:FORM.PLACEHOLDER">
<span data-i18n="MISSING.KEY">Kept</span>
<article data-legal-lang="en" lang="en">EN</article><article data-legal-lang="no" lang="nb" hidden>NO</article>
</body></html>`;

test("applies the Norwegian dictionary to text, attributes, title and meta", () => {
  const out = toNorwegian(page, opts);
  assert.match(out, /<html lang="nb">/);
  assert.match(out, /<title data-i18n-doc-title="SEO.TITLE">Om oss · Mielikkix<\/title>/);
  assert.match(out, /content="Beskrivelse &amp; mer"/);
  assert.match(out, />Agenter<\/a>/);
  assert.match(out, /placeholder="Skriv her"/);
  // A key the dictionary lacks keeps its English text (the browser runtime still tries).
  assert.match(out, />Kept<\/span>/);
});

test("points canonical and og:url at the Norwegian URL", () => {
  const out = toNorwegian(page, opts);
  assert.match(out, /<link rel="canonical" href="https:\/\/mielikkix.ai\/no\/agents\/">/);
  assert.match(out, /property="og:url" content="https:\/\/mielikkix.ai\/no\/agents\/"/);
});

test("rewrites links only to pages that have a Norwegian copy", () => {
  const out = toNorwegian(page, opts);
  assert.match(out, /href="\/no\/agents\/"/);
  assert.match(out, /href="\/blog\/"/);
  assert.match(out, /href="\/pricing\/#chat"/);
  assert.match(out, /href="https:\/\/app.mielikkix.ai\/register\?lang=no"/);
});

test("shows the Norwegian legal article and hides the English one", () => {
  const out = toNorwegian(page, opts);
  assert.match(out, /<article data-legal-lang="en" lang="en" hidden>/);
  assert.match(out, /<article data-legal-lang="no" lang="nb">/);
});
