/**
 * schema.org nodes for Mielikkix's public offerings, each attached ONLY to its
 * canonical page via Layout.astro's `structuredDataNodes` prop (so every page
 * still has one JSON-LD script / one @graph, and each entity is defined once).
 *
 * Descriptions are read from the same English i18n copy the pages render, by
 * item NAME rather than array index, so the markup can't drift from (or silently
 * point at the wrong card in) the visible text.
 *
 * Prices: pricingProductNode() builds a Product with one Offer per tier straight
 * from src/data/pricing.ts (fixed NOK, excl. VAT), so the markup always matches the
 * visible price cards. Not modeled: ratings or reviews, Email Marketing and the other
 * custom-workflow examples, WhatsApp Concierge (not live yet).
 */
import agents from "../assets/i18n/en/agents.json";
import { TIER_NAMES, getProduct, type ProductId } from "../data/pricing";

const SITE = "https://mielikkix.ai/";
const provider = { "@id": `${SITE}#organization` };

function describe(items: { NAME: string; DESCRIPTION: string }[], name: string): string {
  const item = items.find((i) => i.NAME === name);
  if (!item) throw new Error(`[offeringSchema] No "${name}" item in agents.json -- update this file with the rename.`);
  return item.DESCRIPTION;
}

const core = agents.CORE_SOLUTIONS.ITEMS;
const additional = agents.ADDITIONAL_AGENTS.ITEMS;

export const chatWidgetNode = {
  "@type": "SoftwareApplication",
  "@id": `${SITE}#chat-widget`,
  name: "Mielikkix Chat Widget",
  description: describe(core, "Mielikkix Chat Widget"),
  url: `${SITE}features/`,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  provider,
};

export const seoAuditNode = {
  "@type": "SoftwareApplication",
  "@id": `${SITE}#seo-audit-optimize`,
  name: "SEO Audit & Optimize",
  description: describe(core, "SEO Audit & Optimize"),
  url: `${SITE}agent-pricing/`,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  provider,
};

export const voiceReceptionistNode = {
  "@type": "Service",
  "@id": `${SITE}#voice-receptionist`,
  name: "Voice Receptionist",
  description: describe(core, "Voice Receptionist"),
  url: `${SITE}demo/voice-receptionist/`,
  serviceType: "AI voice receptionist",
  provider,
};

export const bookingAssistantNode = {
  "@type": "Service",
  "@id": `${SITE}#booking-assistant`,
  name: "Booking Assistant",
  description: describe(core, "Booking Assistant"),
  url: `${SITE}demo/booking-assistant/`,
  serviceType: "AI booking assistant",
  provider,
};

export const supportTriageNode = {
  "@type": "Service",
  "@id": `${SITE}#support-triage`,
  name: "Support Triage",
  description: describe(additional, "Support Triage"),
  url: `${SITE}demo/support-triage/`,
  serviceType: "AI customer support triage",
  provider,
};

export const reviewReputationNode = {
  "@type": "Service",
  "@id": `${SITE}#review-reputation`,
  name: "Review & Reputation",
  description: describe(additional, "Review & Reputation"),
  url: `${SITE}demo/review-reputation/`,
  serviceType: "AI review and reputation management",
  provider,
};

export const customAgentDevelopmentNode = {
  "@type": "Service",
  "@id": `${SITE}#custom-ai-agent-development`,
  // /agents' own wording: "Plus custom AI agent development for whatever your business needs to automate."
  name: "Custom AI Agent Development",
  // Visible copy: CUSTOM_AGENTS.SUBHEADING + CUSTOM_CTA.SUBHEADING on /agents.
  description: `${agents.CUSTOM_AGENTS.SUBHEADING} ${agents.CUSTOM_CTA.SUBHEADING}`,
  url: `${SITE}agents/`,
  serviceType: "Custom AI agent development",
  provider,
};

/** schema.org Product + one Offer per tier, from the single price list. */
export function pricingProductNode(productId: ProductId, url: string) {
  const product = getProduct(productId);
  return {
    "@type": "Product",
    "@id": `${SITE}#pricing-${product.id}`,
    name: `Mielikkix ${product.name.en}`,
    description: product.tagline.en,
    brand: provider,
    url: `${SITE}${url.replace(/^\//, "")}`,
    offers: product.tiers.map((tier) => {
      const price = tier.priceNokMonthly ?? 0;
      return {
        "@type": "Offer",
        name: `${product.name.en} ${TIER_NAMES[tier.id].en}`,
        price,
        priceCurrency: "NOK",
        availability: "https://schema.org/InStock",
        priceSpecification: {
          "@type": "UnitPriceSpecification",
          price,
          priceCurrency: "NOK",
          unitCode: "MON",
          valueAddedTaxIncluded: false,
          ...(tier.priceFrom ? { minPrice: price } : {}),
        },
      };
    }),
  };
}
