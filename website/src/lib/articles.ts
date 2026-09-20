/**
 * Build-time client for the public articles API (apps/api/app/api/
 * public_articles.py) -- called from Astro frontmatter/getStaticPaths,
 * which runs in Node during `astro build`, NOT in the visitor's browser.
 * This is a genuinely new pattern for this site (every other use of
 * PUBLIC_API_URL is baked into a client-side data attribute for a widget
 * script to read -- see demo.astro) but the correct one given the site's
 * static output: the VPS Postgres database is the source of truth for
 * articles, and this is how a static build actually reads from it.
 *
 * Only ever returns published articles -- the public API itself never
 * returns a draft (see get_public_article_by_slug/list_public_articles),
 * so there is no separate "exclude drafts" filtering needed here.
 */
const API_BASE = import.meta.env.PUBLIC_API_URL;

export interface PublicArticle {
  title: string;
  slug: string;
  excerpt: string | null;
  content: string;
  featured_image_url: string | null;
  meta_title: string | null;
  meta_description: string | null;
  canonical_url: string | null;
  keywords: string[];
  category: string | null;
  tags: string[];
  author_name: string;
  published_at: string;
  updated_at: string;
}

interface PublicArticleListOut {
  items: PublicArticle[];
  total: number;
}

/**
 * Fetch failures (API unreachable at build time, etc.) degrade to an empty
 * list rather than failing the entire site build -- the blog is one
 * section of the site, and a build shouldn't be able to take down every
 * other page because the API happened to be down for a moment. Logged
 * loudly so it's never silently missed.
 */
export async function fetchPublishedArticles(): Promise<PublicArticle[]> {
  try {
    const res = await fetch(`${API_BASE}/api/public/articles?page_size=100`);
    if (!res.ok) {
      console.warn(`[articles] Failed to fetch published articles: HTTP ${res.status}`);
      return [];
    }
    const data: PublicArticleListOut = await res.json();
    return data.items;
  } catch (err) {
    console.warn("[articles] Failed to fetch published articles:", err);
    return [];
  }
}

export async function fetchArticleBySlug(slug: string): Promise<PublicArticle | null> {
  try {
    const res = await fetch(`${API_BASE}/api/public/articles/${encodeURIComponent(slug)}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.warn(`[articles] Failed to fetch article '${slug}':`, err);
    return null;
  }
}
