// Shapes shared by the browser and the route handlers.

import type Anthropic from '@anthropic-ai/sdk';

/** One line of the chat stream (NDJSON). */
export type ChatEvent =
  | { type: 'text'; text: string }
  | { type: 'tool_start'; id: string; name: string; input: unknown }
  | { type: 'tool_done'; id: string; name: string; result: unknown }
  | { type: 'done'; messages: Anthropic.MessageParam[]; stop_reason: string | null; note?: string }
  | { type: 'error'; message: string };

/** A resolver answer, loosely typed: the inspector reads what is there. */
export type Answer = Record<string, unknown> & {
  outcome?: string;
  trace?: string;
  template?: string;
};

export type Rule = {
  rule: string;
  kind?: string;
  owner?: string;
  set_on?: string;
  set_by?: string | null;
  source?: string;
  text?: string;
};
