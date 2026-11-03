import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';
import Designers from './Designers';
import DesignerStorefront from './DesignerStorefront';
import { designerService, type Designer } from '../../services/designerService';
import { filterDesigners, readyDesigners, featuredDesigners } from './designerUtils';
vi.mock('../../components/layout/Layout', () => ({ default: ({ children }: {children: ReactNode}) => <main>{children}</main> }));
vi.mock('../../services/designerService', () => ({ designerService: { listDesigners: vi.fn() } }));
vi.mock('../products/ProductList', () => ({ default: ({initialParams}: {initialParams: {vendor_id: string}}) => <div data-testid="vendor-products">{initialParams.vendor_id}</div> }));
const designer = (id: string, name: string, extra: Partial<Designer> = {}): Designer => ({id, business_name: name, logo_url: '/brand.jpg', total_products: 2, total_orders: 0, created_at: '', ...extra});
const list = [designer('a','ALPHA'), designer('l','LÉMÉ'), designer('n','9 Studio')];
const directory = (path = '/designers') => render(<MemoryRouter initialEntries={[path]}><Designers /></MemoryRouter>);
const storefront = (id: string) => render(<MemoryRouter initialEntries={['/designers/'+id]}><Routes><Route path="/designers/:designerId" element={<DesignerStorefront/>}/></Routes></MemoryRouter>);
beforeEach(() => vi.mocked(designerService.listDesigners).mockReset());
describe('designer discovery', () => {
  it('searches accents and groups non-letter names', () => {
    expect(filterDesigners(list,'leme','All').map(d=>d.id)).toEqual(['l']);
    expect(filterDesigners(list,'','#').map(d=>d.id)).toEqual(['n']);
  });
  it('excludes incomplete visual records and prioritizes curated vendors', () => {
    const ready=readyDesigners([...list, designer('x','',{logo_url:null})]);
    expect(ready).toHaveLength(3);
    expect(featuredDesigners([...ready,designer('f','Featured',{is_featured_storefront:true})]).map(d=>d.id)).toEqual(['f']);
  });
  it('restores search from URL and clears it through alphabetical navigation', async () => {
    vi.mocked(designerService.listDesigners).mockResolvedValue(list);
    directory('/designers?q=leme');
    expect(await screen.findByRole('heading',{name:'Results for “leme”'})).toBeInTheDocument();
    const results=screen.getByRole('region',{name:'Designers A–Z'});
    expect(within(results).getAllByRole('link')).toHaveLength(1);
    expect(within(results).getByRole('link')).toHaveAttribute('href','/designers/l');
    fireEvent.click(screen.getByRole('button',{name:'A'}));
    expect(screen.getByRole('searchbox')).toHaveValue('');
    expect(within(results).getByRole('link')).toHaveAttribute('href','/designers/a');
  });
  it('offers empty-result reset and a recoverable network failure', async () => {
    vi.mocked(designerService.listDesigners).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(list);
    directory('/designers?q=missing');
    fireEvent.click(await screen.findByRole('button',{name:'Try again'}));
    expect(await screen.findByRole('heading',{name:'No designers found'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'Browse all designers'}));
    expect(screen.getByRole('heading',{name:'All designers'})).toBeInTheDocument();
  });
});
describe('public storefront eligibility', () => {
  it('loads the product workflow with the stable vendor ID', async () => {
    vi.mocked(designerService.listDesigners).mockResolvedValue(list); storefront('l');
    expect(await screen.findByTestId('vendor-products')).toHaveTextContent('l');
  });
  it('does not render products for an unavailable vendor', async () => {
    vi.mocked(designerService.listDesigners).mockResolvedValue(list); storefront('private-vendor');
    expect(await screen.findByRole('heading',{name:'Designer unavailable'})).toBeInTheDocument();
    expect(screen.queryByTestId('vendor-products')).not.toBeInTheDocument();
  });
});
