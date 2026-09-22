import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import { FOOTER_DOCUMENTS } from '../../content/footerDocuments';
import { blocksFor } from '../../content/documentBlocks';

export { blocksFor } from '../../content/documentBlocks';
import type { FooterDocumentKey } from '../../content/footerDocuments';

const emailPattern = /[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g;

function LinkedText({ text }: { text: string }) {
  const parts = text.split(emailPattern);
  const emails = text.match(emailPattern) ?? [];
  return <>{parts.map((part, index) => <span key={`${part}-${index}`}>{part}{emails[index] && <a className="underline underline-offset-2" href={`mailto:${emails[index]}`}>{emails[index]}</a>}</span>)}</>;
}

export default function PublicDocument({ documentKey }: { documentKey: FooterDocumentKey }) {
  const document = FOOTER_DOCUMENTS[documentKey];
  const navigate = useNavigate();
  const [orderId, setOrderId] = useState('');
  const [error, setError] = useState('');
  const isTrack = documentKey === 'track';
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = orderId.trim();
    if (!value) { setError('Enter your order ID to continue.'); return; }
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
    const isOrderNumber = /^[a-z0-9][a-z0-9-]{0,49}$/i.test(value);
    if (!isUuid && !isOrderNumber) {
      setError('Use the full order ID or order number from your confirmation or tracking link.');
      return;
    }
    setError('');
    navigate(`/track/${encodeURIComponent(isUuid ? value.toLowerCase() : value)}`);
  };
  return <Layout>
  <div className="mx-auto w-full max-w-4xl px-6 py-14 text-[#1E5053] sm:px-10 lg:py-20" data-document={documentKey}>
    <p className="text-xs font-ui uppercase tracking-[0.3em]">ShopSoma</p>
    <h1 className="mt-4 text-3xl font-serif sm:text-5xl">{document.title}</h1>
    {isTrack && <form onSubmit={submit} className="mt-10 max-w-xl space-y-3 rounded border border-[#1E5053] p-5" aria-label="Track your order">
      <label htmlFor="order-number" className="block text-sm font-ui">Enter your order ID or order number below to see the latest status of your order</label>
      <p id="order-id-help" className="text-sm">Use the full order ID or customer-facing order number from your confirmation or tracking link. You will need access to that order through your account or the original checkout session. You can also <a href={ROUTES.PROFILE_ORDERS} className="underline">view your account orders</a>.</p>
      <div className="flex gap-2"><input id="order-number" aria-describedby="order-id-help" placeholder="Order ID or order number" value={orderId} onChange={(e) => setOrderId(e.target.value)} className="min-w-0 flex-1 border border-[#1E5053] px-3 py-2" /><button className="bg-[#1E5053] px-4 py-2 text-sm text-white" type="submit">Track order</button></div>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </form>}
    {documentKey === 'partner' && <a href={ROUTES.VENDOR_SIGNUP} className="mt-8 inline-flex border border-[#1E5053] px-6 py-3 text-xs font-ui uppercase tracking-[0.2em]">Apply to become a ShopSoma partner</a>}
    {!isTrack && <article className="mt-12 space-y-8 font-serif leading-7">{blocksFor(document.body).map((block, index) => block.kind === 'heading' ? <section key={`${documentKey}-${index}`}><h2 className="mb-2 text-xl font-ui font-medium">{block.lines[0]}</h2></section> : block.kind === 'list' ? <ul key={`${documentKey}-${index}`} className="list-disc space-y-1 pl-6">{block.lines.map((line) => <li key={line}><LinkedText text={line} /></li>)}</ul> : <p key={`${documentKey}-${index}`}><LinkedText text={block.lines.join(' ')} /></p>)}</article>}
  </div>
  </Layout>;
}
