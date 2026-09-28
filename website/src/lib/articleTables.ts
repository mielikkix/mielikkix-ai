/**
 * Gives a bare CMS `<table>` (no attributes) the same bordered, padded look
 * as the hand-styled comparison table in "AI Agents for Small Businesses"
 * -- applied at build time in blog/[slug].astro, so articles can keep plain
 * table markup instead of repeating Tailwind classes on every cell.
 *
 * Only an attribute-less `<table>` is touched: a table that already carries
 * its own classes (like that article's) is left exactly as authored. The
 * wrapper scrolls sideways on narrow screens rather than squeezing columns,
 * and its overflow also clips the header fill to the rounded corners.
 */
const WRAPPER_CLASS = "overflow-x-auto rounded-2xl border border-slate-200";
const TABLE_CLASS = "w-full min-w-[32rem] text-left text-sm";
const TH_CLASS = "bg-slate-50 px-4 py-2 font-semibold";
const TD_CLASS = "border-t border-slate-200 px-4 py-2 align-top";

export function styleBareTables(html: string): string {
  return html.replace(/<table>([\s\S]*?)<\/table>/g, (_match, inner: string) => {
    const cells = inner.replaceAll("<th>", `<th class="${TH_CLASS}">`).replaceAll("<td>", `<td class="${TD_CLASS}">`);
    return `<div class="${WRAPPER_CLASS}"><table class="${TABLE_CLASS}">${cells}</table></div>`;
  });
}
