'use client';

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

// The model's text, as markdown (GFM tables and lists), styled with Tailwind `prose`.
const COMPONENTS: Components = {
  a: ({ href, children, ...props }) => (
    <a href={href} target="_blank" rel="noreferrer noopener" {...props}>
      {children}
    </a>
  ),
};

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <article
      className={
        'prose prose-neutral max-w-none break-words dark:prose-invert prose-p:my-2 prose-table:my-2' +
        (className ? ` ${className}` : '')
      }
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </article>
  );
}
