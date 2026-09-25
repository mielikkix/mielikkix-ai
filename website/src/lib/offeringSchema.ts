/**
 * schema.org nodes for Mielikkix's public offerings, each attached ONLY to its
 * canonical page via Layout.astro's `structuredDataNodes` prop (so every page
 * still has one JSON-LD script / one @graph, and each entity is defined once).
 *
 * Descriptions are read from the same English i18n copy the pages render, by
 * item NAME rather than array index, so the markup can't drift from (or silently
 * point at the wrong card in) the visible text.
 *
 * Deliberately NOT here yet: Offer/price data (Chat Widget and SEO prices are
 * live-converted and the billing currency isn't finalized), Product, ratings or
 * reviews. Not modeled as entities at all: Email Marketing and the other
 * custom-workflow examples, WhatsApp Concierge (demo only).
 */
import agents from "../assets/i18n/en/agents.json";
import agentPricing from "../assets/i18n/en/agent-pricing.json";

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

export const ongoingSeoNode = {
  "@type": "Service",
  "@id": `${SITE}#ongoing-seo`,
  name: "Ongoing SEO",
  // Visible copy: "Ongoing SEO -- we monitor new audit results on your website and keep acting on what the agent finds."
  description: agentPricing.ONGOING.SUBHEADING,
  url: `${SITE}agent-pricing/`,
  serviceType: "Search engine optimization",
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
