export type DocumentBlock = { kind: 'heading' | 'paragraph' | 'list'; lines: string[] };

const EXPLICIT_HEADINGS = new Set([
  'Orders, Returns & General Enquiries', 'Brand & Partnership Enquiries', 'Marketing, Press & Creative Enquiries',
  'International Delivery', 'Ready-To-Wear (RTW)', 'Made-to-Order (MTO)', 'Shipping Costs', 'Split Shipments', 'Tracking Your Order',
  'Return Window', 'Return Conditions', 'Made-to-Order (MTO) Items', 'Final Sale', 'Exchanges', 'Refunds',
  'Delivery Delays', 'Starting a Return', 'Quality Check', 'Return Shipping', 'Damaged, Defective or Incorrect Items', 'Your Statutory Rights',
  'ORDERS & PAYMENT', 'PRODUCTS & SIZING', 'SHIPPING & DELIVERY', 'RETURNS & REFUNDS', 'ACCOUNT & SUPPORT',
  'Partner with SHOPSOMA', 'Brand & Designer Partnerships', 'From Africa, with Style.', '‘Track Your Order’', 'Essential Cookies', 'Preference Cookies', 'Analytics Cookies', 'Marketing Cookies',
]);

const isHeadingLine = (line: string) =>
  /^\d+[.)]\s+/.test(line) || /^[A-Z][A-Z &’'—-]{3,}$/.test(line) || EXPLICIT_HEADINGS.has(line) || /\?$/.test(line);

export function blocksFor(body: string): DocumentBlock[] {
  const lines = body.split(/\r?\n/).map((line) => line.trim());
  const blocks: DocumentBlock[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  const flushParagraph = () => { if (paragraph.length) { blocks.push({ kind: 'paragraph', lines: paragraph }); paragraph = []; } };
  const flushList = () => { if (list.length) { blocks.push({ kind: 'list', lines: list }); list = []; } };
  const appendWrapped = (target: string[], line: string) => {
    const previous = target[target.length - 1];
    if (previous && /[-–—]$/.test(previous)) target[target.length - 1] = `${previous}${line}`;
    else target.push(line);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line) {
      const next = lines.slice(index + 1).find(Boolean);
      const previous = paragraph[paragraph.length - 1];
      // PDF extraction can insert a blank line at a page break inside a
      // sentence. Keep lower-case continuations in the same paragraph while
      // retaining normal blank-line paragraph boundaries.
      if (paragraph.length && previous && next && /^[a-z]/.test(next) && !/[.!?…][\"'”’)]?$/.test(previous)) continue;
      flushList(); flushParagraph(); continue;
    }
    if (line.startsWith('•')) { flushParagraph(); list.push(line.slice(1).trim()); continue; }
    if (list.length) {
      const previous = list[list.length - 1];
      // A completed bullet followed by prose starts a new paragraph, even
      // when the source extraction omitted the separating blank line.
      if (/[.!?]["'”’)]?$/.test(previous)) { flushList(); }
      else {
        const lastIndex = list.length - 1;
        const separator = /[-–—]$/.test(previous) ? '' : ' ';
        list[lastIndex] = `${previous}${separator}${line}`;
        continue;
      }
    }
    if (line.endsWith('-') && lines[index + 1]) {
      const joined = `${line}${lines[index + 1]}`;
      if (joined.endsWith('?')) { flushParagraph(); blocks.push({ kind: 'heading', lines: [joined] }); index += 1; continue; }
    }
    if (isHeadingLine(line)) { flushParagraph(); blocks.push({ kind: 'heading', lines: [line] }); }
    else appendWrapped(paragraph, line);
  }
  flushList(); flushParagraph();
  return blocks;
}
