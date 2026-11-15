import { createAgent, registerTools } from '@ui-sdk/react/agent';

/**
 * Lets an AI agent read and operate the page's controls by name (snapshot / act / query), and a browser's own
 * agent through WebMCP. Controls marked `data-agent-confirm` (the confirm dialog's Continue) stay with the person.
 */
export function startAgent() {
  const agent = createAgent();
  // without an allow of its own, the bridge already refuses marked steps with "Needs a person"
  const unregister = registerTools(agent, { allow: (step) => !step.confirm });
  return { agent, unregister };
}
