// The model's tools: the MCP server's tool set and instructions, mirrored
// (src/tkg/mcp/server.py). Every call goes to the resolver as this process's
// person. No tool takes a persona, and there is no tool that fetches a document.

import type Anthropic from '@anthropic-ai/sdk';
import { call, type Json } from './resolver';

export const INSTRUCTIONS = `You are connected to a firm's knowledge layer as one specific person, fixed for this
session — call whoami() to see who. Everything you are shown has already been
decided for that person: never suggest another person could ask instead.

Questions are answered by competency-question templates, never by free-form queries.
Call questions() once, pick the template that fits, and fill its slots. Slots take
short identifiers: matters like M-2022-0117, clients like C-0042, people like
P-0101, and vocabulary like gl:matter-type/regulatory-investigation or
id:jurisdiction/NL. Defaults are used for slots you leave out.

Business words are not yours to interpret. Before filling a slot from a word the
user used — "AIFM", "AFM investigation", "active client" — call resolve_term() on it
and use what it says the word means, then pass the term ids you relied on in
ask(..., terms=[...]). If a term has several readings, do not pick one: show the
readings, their owners and their counts, and ask the user which they mean.

Report what comes back faithfully:
- Every row cites the named graph it came from; keep the citation.
- A fact whose review state is "unconfirmed" must be reported as unconfirmed.
- A matter with no outcome has no outcome. Do not supply one.
- If the outcome is refused, refused-aggregate, or answered-with-withheld, say so
  and quote the rule, owner and date from explain. Do not guess what was withheld,
  and do not try to reconstruct it from other questions.
`;

const obj = (properties: Record<string, unknown>, required: string[] = []) =>
  ({ type: 'object', properties, required, additionalProperties: false }) as Anthropic.Tool.InputSchema;
const str = (description?: string) => ({ type: 'string', ...(description ? { description } : {}) });

export const TOOLS: Anthropic.Tool[] = [
  {
    name: 'whoami',
    description: 'Who this session is. Fixed when the session started; no tool changes it.',
    input_schema: obj({}),
  },
  {
    name: 'questions',
    description:
      'The competency questions the knowledge layer answers, with their slots and defaults.',
    input_schema: obj({}),
  },
  {
    name: 'ask',
    description: `Ask one competency question, e.g. ask("CQ-06", {"matter": "M-2021-0043"}).

\`terms\` lists the glossary term ids you used to fill the slots, so the answer
records which definitions it rests on. Returns rows with the named graph each
came from, the route and why, the outcome, and — when anything was withheld —
explain: the rule, its owner, the date it was set, and how many facts were
blocked directly or by lineage. An answered question also carries a
short-lived permit for passages().`,
    input_schema: obj(
      {
        question_id: str(),
        slots: { type: 'object', additionalProperties: { type: 'string' } },
        terms: { type: 'array', items: { type: 'string' } },
      },
      ['question_id'],
    ),
  },
  {
    name: 'resolve_term',
    description: `What a business word means in this firm, and who decides that.

Returns the glossary entry — definition, owner, the slot values it stands
for — or, for a word with several readings, every reading with its owner
and its count as you are allowed to see it. Call this before interpreting
any business term yourself.`,
    input_schema: obj({ text: str() }, ['text']),
  },
  {
    name: 'audit_subject',
    description: `Risk & Compliance only: who has ever been shown anything derived from a matter.

Anyone else is refused, and the attempt is recorded.`,
    input_schema: obj({ matter: str() }, ['matter']),
  },
  {
    name: 'audit_person',
    description: `Risk & Compliance only: what one person was shown, between two ISO times.

\`person\` is who is being asked about, not who is asking — that is fixed.`,
    input_schema: obj({ person: str(), since: str(), until: str() }, ['person']),
  },
  {
    name: 'audit_trace',
    description:
      'Risk & Compliance only: the full stored record of one decision, identifiers resolved.',
    input_schema: obj({ trace: str() }, ['trace']),
  },
  {
    name: 'explain',
    description: 'Why one of your earlier questions was decided as it was, from the stored record.',
    input_schema: obj({ trace: str() }, ['trace']),
  },
  {
    name: 'passages',
    description: `Passages from the document index, limited to what ask() permitted.

Needs the permit returned by ask(); the permitted matters are applied as a
filter inside the index query, so nothing else is ever scored. Each passage
carries a source_url that opens the PDF, minted with your own credentials
and valid for minutes. There is no tool that fetches a document by id.`,
    input_schema: obj({ permit: str(), text: str() }, ['permit']),
  },
];

type Input = Record<string, unknown>;
const s = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null);
const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
const record = (v: unknown): Record<string, string> =>
  v && typeof v === 'object' && !Array.isArray(v)
    ? Object.fromEntries(Object.entries(v).filter(([, x]) => typeof x === 'string')) as Record<string, string>
    : {};

/** Run one tool call against the resolver. Input is validated here: the model's
 *  arguments are untrusted, and only the declared fields are forwarded. */
export async function runTool(name: string, raw: unknown): Promise<Json> {
  const input = (raw && typeof raw === 'object' ? raw : {}) as Input;
  const need = (field: string) => {
    const v = s(input[field]);
    if (v === null) throw new ToolInputError(`${name}: ${field} is required`);
    return v;
  };
  switch (name) {
    case 'whoami':
      return call('GET', '/whoami');
    case 'questions':
      return call('GET', '/templates');
    case 'ask':
      return call('POST', '/ask', {
        template_id: need('question_id'),
        slots: record(input.slots),
        terms: strings(input.terms),
      });
    case 'resolve_term':
      return call('POST', '/resolve_term', { text: need('text') });
    case 'audit_subject':
      return call('POST', '/audit/subject', { matter: need('matter') });
    case 'audit_person':
      return call('POST', '/audit/person', {
        person: need('person'),
        since: s(input.since),
        until: s(input.until),
      });
    case 'audit_trace':
      return call('POST', '/audit/trace', { trace: need('trace') });
    case 'explain':
      return call('POST', '/explain', { trace: need('trace') });
    case 'passages':
      return call('POST', '/passages', { permit: need('permit'), text: s(input.text) ?? '' });
    default:
      throw new ToolInputError(`no tool named ${name}`);
  }
}

export class ToolInputError extends Error {}
