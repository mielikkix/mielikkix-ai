// Builds the Norwegian site at /no/ (QA 2026-10-05, BUG-13: Norwegian had no
// URL of its own, so it could not be indexed, shared or linked to).
//
// Every page is written once, in English, with data-i18n keys on its
// translatable text (see src/lib/i18n/translationService.ts, which swaps them
// in the browser). After the build, this applies the Norwegian JSON to those
// same keys and writes the result to dist/no/<path>/index.html, so the
// Norwegian copy is real, crawlable HTML rather than English HTML that only
// turns Norwegian once JavaScript has run. One source of truth for text, no
// second set of page components to keep in sync.
//
// A page gets a copy when Layout.astro gave it an hreflang="nb" alternate
// (pages with a translation namespace, and the legal pages). Blog posts are
// English-only and stay that way.
//
// The transform works on Astro's own output, which is predictable: double-
// quoted attributes, and data-i18n elements that hold plain text only (the
// browser runtime replaces their textContent, so they can't hold markup).
// Anything it can't match is left in English and still gets translated in the
// browser, exactly as before.

import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const I18N_DIR = fileURLToPath(new URL("../src/assets/i18n/no/", import.meta.url));
const TITLE_SUFFIX = " · Mielikkix";

const TAG_RE = /<([a-zA-Z][\w-]*)((?:\s+[^\s=<>"/]+(?:="[^"]*")?)*)\s*(\/?)>/g;
const LEAF_RE = /<([a-zA-Z][\w-]*)((?:\s+[^\s=<>"/]+(?:="[^"]*")?)*)\s*>([^<]*)<\/\1>/g;

const escapeText = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const escapeAttr = (s) => escapeText(s).replace(/"/g, "&quot;");

function attr(attrs, name) {
  const m = attrs.match(new RegExp(`\\s${name}="([^"]*)"`));
  return m ? m[1] : null;
}

function setAttr(attrs, name, value) {
  const re = new RegExp(`(\\s${name}=)"[^"]*"`);
  const encoded = `"${escapeAttr(value)}"`;
  return re.test(attrs) ? attrs.replace(re, `$1${encoded}`) : `${attrs} ${name}=${encoded}`;
}

/** Dot-path lookup, same as translationService.ts's t(); null when missing. */
function lookup(dict, key) {
  const value = key.split(".").reduce((acc, seg) => (acc != null && typeof acc === "object" ? acc[seg] : undefined), dict);
  return typeof value === "string" ? value.replace("{{YEAR}}", String(new Date().getFullYear())) : null;
}

async function loadDict(namespaces) {
  const dict = {};
  for (const ns of namespaces) {
    try {
      Object.assign(dict, JSON.parse(await readFile(path.join(I18N_DIR, `${ns}.json`), "utf8")));
    } catch {
      /* no such namespace: those keys stay English and are translated in the browser */
    }
  }
  return dict;
}

async function listHtml(dir, base = dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (path.relative(base, full) === "no") continue;
      out.push(...(await listHtml(full, base)));
    } else if (entry.name.endsWith(".html")) {
      out.push(full);
    }
  }
  return out;
}

function routeOf(distDir, file) {
  const rel = path.relative(distDir, file).split(path.sep).join("/");
  if (rel === "index.html") return "/";
  return rel.endsWith("/index.html") ? `/${rel.slice(0, -"index.html".length)}` : null;
}

function norwegianHref(href, twins) {
  if (!href.startsWith("/") || href.startsWith("//")) return null;
  const cut = href.search(/[?#]/);
  const pathname = cut === -1 ? href : href.slice(0, cut);
  const rest = cut === -1 ? "" : href.slice(cut);
  const normalized = pathname.endsWith("/") || pathname.includes(".") ? pathname : `${pathname}/`;
  return twins.has(normalized) ? `/no${normalized}${rest}` : null;
}

export function toNorwegian(html, { dict, twins, site, route }) {
  const titleSuffix = /<body[^>]*\sdata-title-suffix="off"/.test(html) ? "" : TITLE_SUFFIX;
  const norwegianUrl = new URL(`/no${route}`, site).toString();

  // 1. Attributes, one opening tag at a time.
  let out = html.replace(TAG_RE, (tag, name, attrs, selfClose) => {
    let a = attrs;
    const lower = name.toLowerCase();
    // "nb" (Bokmål), the same tag as hreflang -- QA 2026-10-08, W-07.
    if (lower === "html") a = setAttr(a, "lang", "nb");

    const spec = attr(a, "data-i18n-attr");
    if (spec) {
      for (const pair of spec.split(";")) {
        const [attrName, key] = pair.split(":").map((p) => p.trim());
        const value = attrName && key ? lookup(dict, key) : null;
        if (value !== null) a = setAttr(a, attrName, value);
      }
    }
    const metaTitle = attr(a, "data-i18n-meta-title");
    if (metaTitle && lookup(dict, metaTitle) !== null) a = setAttr(a, "content", lookup(dict, metaTitle) + titleSuffix);
    const metaDesc = attr(a, "data-i18n-meta-desc");
    if (metaDesc && lookup(dict, metaDesc) !== null) a = setAttr(a, "content", lookup(dict, metaDesc));

    if (lower === "link" && attr(a, "rel") === "canonical") a = setAttr(a, "href", norwegianUrl);
    if (lower === "meta" && attr(a, "property") === "og:url") a = setAttr(a, "content", norwegianUrl);
    if (lower === "meta" && attr(a, "property") === "og:locale") a = setAttr(a, "content", "nb_NO");

    // LegalLayout renders both articles and hides the Norwegian one.
    const legal = attr(a, "data-legal-lang");
    if (legal === "no") a = a.replace(/\shidden(?=\s|$)/, "");
    if (legal === "en" && !/\shidden(?=\s|$)/.test(a)) a += " hidden";

    if (lower === "a") {
      const href = attr(a, "href");
      const target = href ? norwegianHref(href, twins) : null;
      if (target) a = setAttr(a, "href", target);
      // The sign-up page opens in Norwegian too (apps/dashboard's shared/authLang.ts).
      if (href && /^https:\/\/app\.mielikkix\.ai\/register\/?$/.test(href)) a = setAttr(a, "href", `${href}?lang=no`);
    }

    // LanguageSwitcher's server-rendered "EN" (the browser fixes it too, a moment later).
    if (lower === "img" && /\blang-active-flag\b/.test(attr(a, "class") ?? "")) a = setAttr(a, "src", "/flags/no.svg");

    return `<${name}${a}${selfClose ? " /" : ""}>`;
  });

  // 2. Text of leaf elements.
  out = out.replace(LEAF_RE, (whole, name, attrs, text) => {
    if (/\blang-active-label\b/.test(attr(attrs, "class") ?? "")) return `<${name}${attrs}>NOR</${name}>`;
    const docTitle = attr(attrs, "data-i18n-doc-title");
    if (docTitle) {
      const value = lookup(dict, docTitle);
      return value === null ? whole : `<${name}${attrs}>${escapeText(value + titleSuffix)}</${name}>`;
    }
    const key = attr(attrs, "data-i18n");
    if (!key) return whole;
    const value = lookup(dict, key);
    return value === null ? whole : `<${name}${attrs}>${escapeText(value)}</${name}>`;
  });

  return out;
}

export default function norwegianPages() {
  return {
    name: "mielikkix-norwegian-pages",
    hooks: {
      "astro:build:done": async ({ dir, logger }) => {
        const distDir = fileURLToPath(dir);
        const site = "https://mielikkix.ai";
        const pages = [];
        for (const file of await listHtml(distDir)) {
          const route = routeOf(distDir, file);
          if (!route) continue;
          const html = await readFile(file, "utf8");
          if (html.includes('hreflang="nb"')) pages.push({ route, html });
        }
        const twins = new Set(pages.map((p) => p.route));
        const common = await loadDict(["common", "footer"]);

        for (const { route, html } of pages) {
          const page = html.match(/<body[^>]*\sdata-page="([^"]+)"/)?.[1];
          const dict = { ...common, ...(page ? await loadDict([page]) : {}) };
          const target = path.join(distDir, "no", ...route.split("/").filter(Boolean), "index.html");
          await mkdir(path.dirname(target), { recursive: true });
          await writeFile(target, toNorwegian(html, { dict, twins, site, route }));
        }

        // Norwegian URLs in the sitemap @astrojs/sitemap wrote just before this hook.
        const sitemapFile = path.join(distDir, "sitemap-0.xml");
        try {
          const xml = await readFile(sitemapFile, "utf8");
          const entries = [...twins]
            .sort()
            .map((route) => `<url><loc>${new URL(`/no${route}`, site).toString()}</loc></url>`)
            .join("");
          await writeFile(sitemapFile, xml.replace("</urlset>", `${entries}</urlset>`));
        } catch {
          logger.warn("sitemap-0.xml not found; Norwegian URLs not added to the sitemap");
        }
        logger.info(`Norwegian copies written for ${twins.size} pages under /no/`);
      },
    },
  };
}
