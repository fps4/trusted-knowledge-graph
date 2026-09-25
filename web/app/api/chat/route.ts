// Chat: Claude, through the Anthropic API directly, with the MCP server's tools.
// Every tool call is a resolver call as this process's person. The stream to the
// browser is NDJSON: text deltas, tool_start, tool_done, then done or error.
// docs/decisions/0027.

import Anthropic from '@anthropic-ai/sdk';
import { INSTRUCTIONS, TOOLS, ToolInputError, runTool } from '@/lib/server/tools';
import type { ChatEvent } from '@/lib/types';

export const dynamic = 'force-dynamic';

const MODEL = process.env.TKG_MODEL || 'claude-opus-5-5';
const MAX_STEPS = 10;

function describe(err: unknown): string {
  if (err instanceof Anthropic.AuthenticationError) return 'The Anthropic API rejected the key.';
  if (err instanceof Anthropic.RateLimitError) return 'The Anthropic API is rate-limiting; try again shortly.';
  if (err instanceof Anthropic.APIConnectionError) return 'Could not reach the Anthropic API. Guided mode works offline.';
  if (err instanceof Anthropic.APIError) return `The Anthropic API answered ${err.status ?? 'with an error'}.`;
  return 'The chat failed. Guided mode works without the model.';
}

export async function POST(request: Request) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return Response.json(
      { error: 'no-key', message: 'Chat needs ANTHROPIC_API_KEY on the host. Guided mode needs no model.' },
      { status: 503 },
    );
  }
  const body = (await request.json().catch(() => ({}))) as { history?: unknown; prompt?: unknown };
  const prompt = typeof body.prompt === 'string' ? body.prompt.trim() : '';
  if (!prompt) return Response.json({ error: 'empty', message: 'Nothing to ask.' }, { status: 400 });
  // The earlier turns, exactly as the API returned them (thinking blocks included):
  // the conversation is only ever appended to.
  const history = Array.isArray(body.history) ? (body.history as Anthropic.MessageParam[]) : [];

  const client = new Anthropic({ apiKey });
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const emit = (event: ChatEvent) => controller.enqueue(encoder.encode(JSON.stringify(event) + '\n'));
      const messages: Anthropic.MessageParam[] = [...history, { role: 'user', content: prompt }];
      try {
        for (let step = 0; step < MAX_STEPS; step++) {
          const turn = client.messages.stream(
            {
              model: MODEL,
              max_tokens: 16000,
              system: INSTRUCTIONS,
              tools: TOOLS,
              tool_choice: { type: 'auto' },
              output_config: { effort: 'low' },
              messages,
            },
            { signal: request.signal },
          );
          turn.on('text', (delta) => emit({ type: 'text', text: delta }));
          const message = await turn.finalMessage();

          // Stop reasons first, before anything in the content is acted on.
          if (message.stop_reason === 'refusal') {
            emit({ type: 'error', message: 'The model declined to continue this turn.' });
            emit({ type: 'done', messages: history, stop_reason: 'refusal' });
            return;
          }
          const uses = message.content.filter((b): b is Anthropic.ToolUseBlock => b.type === 'tool_use');
          if (message.stop_reason === 'max_tokens' && uses.length > 0) {
            emit({ type: 'error', message: 'The model ran out of room mid-tool-call; nothing was run.' });
            emit({ type: 'done', messages: history, stop_reason: 'max_tokens' });
            return;
          }
          messages.push({ role: 'assistant', content: message.content });
          if (message.stop_reason !== 'tool_use' || uses.length === 0) {
            emit({
              type: 'done',
              messages,
              stop_reason: message.stop_reason,
              note: message.stop_reason === 'max_tokens' ? 'The answer was cut off at the length limit.' : undefined,
            });
            return;
          }

          const results: Anthropic.ToolResultBlockParam[] = [];
          for (const use of uses) {
            emit({ type: 'tool_start', id: use.id, name: use.name, input: use.input });
            try {
              const result = await runTool(use.name, use.input);
              emit({ type: 'tool_done', id: use.id, name: use.name, result });
              results.push({ type: 'tool_result', tool_use_id: use.id, content: JSON.stringify(result) });
            } catch (err) {
              const reason = err instanceof ToolInputError ? err.message : 'the tool failed';
              emit({ type: 'tool_done', id: use.id, name: use.name, result: { outcome: 'error', reason } });
              results.push({ type: 'tool_result', tool_use_id: use.id, is_error: true, content: reason });
            }
          }
          messages.push({ role: 'user', content: results });
        }
        emit({ type: 'error', message: `Stopped after ${MAX_STEPS} steps.` });
        emit({ type: 'done', messages, stop_reason: null });
      } catch (err) {
        if (!request.signal.aborted) emit({ type: 'error', message: describe(err) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: { 'Content-Type': 'application/x-ndjson; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
