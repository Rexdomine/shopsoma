import { describe, expect, it } from 'vitest';
import { FOOTER_SECTIONS } from '../../components/layout/Footer';
import { FOOTER_DOCUMENTS } from '../../content/footerDocuments';
import { blocksFor } from './PublicDocument';

describe('footer document contract', () => {
  it('keeps the three groups and ten links in client order', () => {
    expect(FOOTER_SECTIONS.map((section) => section.title)).toEqual(['Customer Care', 'About ShopSoma', 'Policies']);
    expect(FOOTER_SECTIONS.flatMap((section) => section.links.map((link) => [link.label, link.to]))).toEqual([
      ['Contact Us', '/contact'], ['Track your order', '/track'], ['Shipping', '/shipping'], ['Returns and Refunds', '/returns'], ['FAQ', '/faqs'],
      ['About Us', '/about'], ['Become a ShopSoma partner', '/collaborate'], ['Terms of Use', '/terms'], ['Privacy Policy', '/privacy'], ['Cookie Policy', '/cookies'],
    ]);
  });

  it('has ten distinct, sourced documents with meaningful content', () => {
    const docs = Object.values(FOOTER_DOCUMENTS);
    expect(docs).toHaveLength(10);
    expect(new Set(docs.map((doc) => doc.body)).size).toBe(10);
    for (const doc of docs) expect(doc.title.length * doc.source.length * doc.body.length).toBeGreaterThan(0);
  });

  it('preserves normalized source order, headings, and bullets for every document', () => {
    const normalize = (value: string) => value.replace(/•\s*/g, '').replace(/\s+/g, ' ').trim();
    for (const document of Object.values(FOOTER_DOCUMENTS)) {
      const blocks = blocksFor(document.body);
      const rendered = blocks.flatMap((block) => block.lines).join(' ');
      expect(normalize(rendered)).toBe(normalize(document.body));
      expect(blocks.some((block) => block.kind === 'heading')).toBe(true);
      if (document.body.includes('•')) expect(blocks.some((block) => block.kind === 'list')).toBe(true);
    }
  });
});
