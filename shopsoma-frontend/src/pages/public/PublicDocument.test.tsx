import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import PublicDocument from './PublicDocument';
import Footer from '../../components/layout/Footer';
import { FOOTER_DOCUMENTS } from '../../content/footerDocuments';
import type { FooterDocumentKey } from '../../content/footerDocuments';
import { subscribeToNewsletter } from '../../services/newsletterService';
vi.mock('../../components/layout/Layout', () => ({ default: ({ children }: { children: ReactNode }) => <main>{children}</main> }));
vi.mock('../../services/newsletterService', () => ({ subscribeToNewsletter: vi.fn() }));
const normalize = (text: string) => text.replace(/•/g, '').replace(/\s/g, '');
function Location() { return <output data-testid="location">{useLocation().pathname}</output>; }
function show(key: FooterDocumentKey) { return render(<MemoryRouter><PublicDocument documentKey={key} /><Location /></MemoryRouter>); }
beforeEach(() => { vi.clearAllMocks(); });
describe('public footer documents', () => {
  it.each(Object.keys(FOOTER_DOCUMENTS) as FooterDocumentKey[])('preserves all %s article copy in source order', (key) => {
    const { container } = show(key);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(FOOTER_DOCUMENTS[key].title);
    expect(normalize(container.querySelector('article')!.textContent!)).toBe(normalize(FOOTER_DOCUMENTS[key].body));
  });
  it('uses the layout main landmark without nesting another main', () => {
    const { container } = show('shipping');
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(container.querySelector('main > div[data-document="shipping"]')).toBeInTheDocument();
  });

  it('keeps wrapped shipping prose out of headings and renders section headings', () => {
    show('shipping');
    expect(screen.getByRole('heading', { name: 'Shipping Costs' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /We deliver SHOPSOMA/ })).not.toBeInTheDocument();
  });
  it('joins the wrapped FAQ question into one heading', () => {
    show('faq');
    expect(screen.getByRole('heading', { name: /What is the difference between Ready-to-Wear and Made-to-\s*Order\?/ })).toBeInTheDocument();
  });
  it('links the exact contact email addresses', () => {
    show('contact');
    for (const email of ['contact@shopsoma.com', 'partnerships@shopsoma.com', 'marketing@shopsoma.com']) expect(screen.getByRole('link', { name: email })).toHaveAttribute('href', `mailto:${email}`);
  });
  it('validates empty and invalid tracking IDs before using the existing route', () => {
    show('track');
    fireEvent.click(screen.getByRole('button', { name: 'Track order' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your order ID');
    fireEvent.change(screen.getByLabelText(/Enter your order details/), { target: { value: 'order/one?two' } });
    fireEvent.click(screen.getByRole('button', { name: 'Track order' }));
    expect(screen.getByRole('alert')).toHaveTextContent('not the order number');
    expect(screen.getByTestId('location')).toHaveTextContent('/');
    fireEvent.change(screen.getByLabelText(/Enter your order details/), { target: { value: ' 12345678-1234-1234-1234-123456789ABC ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Track order' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/track/12345678-1234-1234-1234-123456789abc');
  });
  it('keeps partner application on the existing vendor signup path', () => {
    show('partner');
    expect(screen.getByRole('link', { name: 'Apply to become a ShopSoma partner' })).toHaveAttribute('href', '/vendor/signup');
  });
});
describe('footer interactions', () => {
  it('opens and closes mobile sections with accessible state', () => {
    render(<MemoryRouter><Footer /></MemoryRouter>);
    const policies = screen.getByRole('button', { name: /Policies/ });
    expect(policies).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(policies);
    expect(policies).toHaveAttribute('aria-expanded', 'true');
    const panel = document.getElementById(policies.getAttribute('aria-controls')!)!;
    expect(within(panel).getAllByRole('link')).toHaveLength(3);
    fireEvent.click(policies);
    expect(policies).toHaveAttribute('aria-expanded', 'false');
  });
  it('preserves newsletter submission', async () => {
    vi.mocked(subscribeToNewsletter).mockResolvedValue({ message: 'Subscribed successfully' } as Awaited<ReturnType<typeof subscribeToNewsletter>>);
    render(<MemoryRouter><Footer /></MemoryRouter>);
    const inputs = screen.getAllByPlaceholderText('example@mail.com');
    fireEvent.change(inputs[0], { target: { value: 'reader@example.com' } });
    fireEvent.submit(inputs[0].closest('form')!);
    await waitFor(() => expect(subscribeToNewsletter).toHaveBeenCalledWith({ email: 'reader@example.com' }));
  });
});
