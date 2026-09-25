import { Workspace } from '@/components/workspace';

// Read at request time: the image is one build, the person is the container's.
export const dynamic = 'force-dynamic';

export default function Page() {
  const persona = process.env.TKG_PERSONA || '';
  const model = process.env.ANTHROPIC_API_KEY ? process.env.TKG_MODEL || 'claude-opus-5-5' : null;
  return <Workspace persona={persona} model={model} />;
}
