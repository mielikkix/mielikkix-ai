// Run: npm test  (node --test, Node 22+ strips the TypeScript types itself)
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  products,
  bundles,
  bundleListPrice,
  bundleSaving,
  formatMonthly,
  formatYearly,
  getTier,
  pricePerUnit,
  type ProductId,
} from "../src/data/pricing.ts";

test("every product has 3-4 tiers and exactly one recommended (Business) tier", () => {
  for (const p of products) {
    assert.ok(p.tiers.length >= 3 && p.tiers.length <= 4, `${p.id} has ${p.tiers.length} tiers`);
    const recommended = p.tiers.filter((t) => t.recommended);
    assert.equal(recommended.length, 1, `${p.id} must have exactly one recommended tier`);
    assert.equal(recommended[0].id, "business", `${p.id}: the recommended tier must be Business`);
  }
});

test("tier order is Free -> Start -> Business -> Growth, and Free exists only for Chat Widget and SEO", () => {
  const order = ["free", "start", "business", "growth"];
  for (const p of products) {
    const ids = p.tiers.map((t) => t.id);
    assert.deepEqual(ids, order.filter((id) => ids.includes(id as never)), `${p.id} tiers out of order`);
    assert.equal(ids.includes("free"), p.id === "chat-widget" || p.id === "seo-audit", `${p.id} free tier`);
  }
});

test("prices match the agreed NOK price list", () => {
  const expected: Record<ProductId, (number | null)[]> = {
    "chat-widget": [null, 490, 990, 1990],
    "voice-receptionist": [590, 1790, 3990],
    "booking-assistant": [390, 890, 1790],
    "support-triage": [990, 2490, 4990],
    "review-reputation": [390, 890, 1990],
    "seo-audit": [null, 490, 5900, 9900],
    "custom-agents": [2990, 6990, 14900],
  };
  for (const p of products) {
    assert.deepEqual(p.tiers.map((t) => t.priceNokMonthly), expected[p.id], p.id);
  }
});

test("bundle prices are lower than the sum of their parts, and match the agreed list sums", () => {
  for (const b of bundles) {
    assert.ok(b.priceNokMonthly < bundleListPrice(b), `${b.id} is not cheaper than its parts`);
    assert.equal(bundleSaving(b), bundleListPrice(b) - b.priceNokMonthly);
  }
  assert.equal(bundleListPrice(bundles.find((b) => b.id === "front-desk")!), 3670);
  assert.equal(bundleListPrice(bundles.find((b) => b.id === "visibility")!), 1870);
});

test("voice overage and effective per-minute prices", () => {
  const voice = ["start", "business", "growth"].map((id) => getTier("voice-receptionist", id as never));
  assert.deepEqual(voice.map((t) => t.overage?.priceNok), [4, 3.5, 3]);
  assert.deepEqual(voice.map((t) => pricePerUnit(t)!.toFixed(2)), ["5.90", "3.58", "2.66"]);
});

test("price formatting: Norwegian uses NBSP thousands and 'eks. mva.', English 'excl. VAT'", () => {
  const growth = getTier("chat-widget", "growth");
  assert.equal(formatMonthly(growth, "no"), "1 990 kr/mnd eks. mva.");
  assert.equal(formatMonthly(growth, "en"), "NOK 1,990/month excl. VAT");
  assert.equal(formatYearly(growth, "no"), "19 900 kr/år eks. mva.");
  assert.equal(formatMonthly(getTier("custom-agents", "growth"), "no"), "fra 14 900 kr/mnd eks. mva.");
  assert.equal(formatMonthly(getTier("chat-widget", "free"), "en"), "Free");
});
