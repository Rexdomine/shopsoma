import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import VendorProductAdd from './VendorProductAdd';
import VendorProductEdit from './VendorProductEdit';

const mocks = vi.hoisted(() => ({
  createProduct: vi.fn(), uploadImage: vi.fn(), getVendorProduct: vi.fn(), updateProduct: vi.fn(),
  warning: vi.fn(), success: vi.fn(), error: vi.fn(), hideToast: vi.fn(),
}));
vi.mock('../../services/productService', () => ({ productService: mocks }));
vi.mock('../../services/categoryService', () => ({ categoryService: {
  getPrimaryCategories: async () => [{ id: 'women', name: 'Women' }],
  getSubcategories: async () => [],
} }));
vi.mock('../../services/collectionService', () => ({ collectionService: { getCollections: async () => [] } }));
vi.mock('../../hooks/useToast', () => ({ useToast: () => ({ ...mocks, toasts: [] }) }));
vi.mock('../../components/vendor/VendorSidebar', () => ({ default: () => null }));
vi.mock('../../components/vendor/CollectionModal', () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:preview'), revokeObjectURL: vi.fn() }));
  mocks.uploadImage.mockResolvedValue({ original: 'https://example.test/linen.jpg' });
  mocks.createProduct.mockResolvedValue({ id: 'new' });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function mount() {
  const result = render(<MemoryRouter><VendorProductAdd /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Select category' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Women' }));
  return result;
}
function selectMaterial(value: string, current = 'Select materials') {
  fireEvent.click(screen.getByRole('button', { name: current }));
  fireEvent.click(screen.getByRole('button', { name: value }));
}
function submit(container: HTMLElement) { fireEvent.submit(container.querySelector('form')!); }
async function fillProduct(container: HTMLElement, mode: 'single' | 'variable') {
  fireEvent.change(screen.getByPlaceholderText('Enter product name'), { target: { value: 'Linen shirt' } });
  fireEvent.change(screen.getByPlaceholderText('Describe your product'), { target: { value: 'A linen shirt' } });
  fireEvent.change(screen.getAllByPlaceholderText('0.00')[0], { target: { value: '100' } });
  for (const label of ['Weight (kg)', 'Length (cm)', 'Width (cm)', 'Height (cm)']) {
    fireEvent.change(screen.getByText(`${label} *`).parentElement!.querySelector('input')!, { target: { value: '1' } });
  }
  if (mode === 'single') {
    fireEvent.change(screen.getByPlaceholderText('E.g., Black'), { target: { value: 'Black' } });
    fireEvent.click(screen.getByRole('button', { name: 'M' }));
  } else {
    fireEvent.click(screen.getByRole('button', { name: 'Variable Product' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add Variation' }));
    const colorModes = screen.getAllByRole('combobox').filter(el => el.textContent?.includes('No Color'));
    fireEvent.change(colorModes[colorModes.length - 1], { target: { value: 'none' } });
  }
  const inputs = container.querySelectorAll('input[type="file"]');
  fireEvent.change(inputs[inputs.length - 1], { target: { files: [new File(['image'], 'linen.jpg', { type: 'image/jpeg' })] } });
  await waitFor(() => expect(container.querySelector('img[src="blob:preview"]')).not.toBeNull());
  if (mode === 'variable') fireEvent.click(screen.getByRole('button', { name: 'Save Variation' }));
}

describe('custom product materials', () => {
  it.each(['single', 'variable'] as const)('submits trimmed custom text for a %s product', async mode => {
    const { container } = await mount();
    await fillProduct(container, mode);
    selectMaterial('Others');
    const input = screen.getByLabelText('Custom material *');
    expect(input).toHaveAttribute('maxlength', '5000');
    fireEvent.change(input, { target: { value: '  70% linen, 30% hemp  ' } });
    submit(container);
    await waitFor(() => expect(mocks.createProduct).toHaveBeenCalledWith(expect.objectContaining({
      fabric_composition: '70% linen, 30% hemp', product_type: mode, status: 'draft',
    })));
  });
  it.each(['', '   '])('blocks empty custom text (%j)', async value => {
    const { container } = await mount();
    selectMaterial('Others');
    fireEvent.change(screen.getByLabelText('Custom material *'), { target: { value } });
    submit(container);
    expect(mocks.warning).toHaveBeenCalledWith('Please enter a custom material', 'Missing info');
    expect(mocks.createProduct).not.toHaveBeenCalled();
  });
  it('uses a preset after switching away from a custom material', async () => {
    const { container } = await mount();
    await fillProduct(container, 'single');
    selectMaterial('Others');
    fireEvent.change(screen.getByLabelText('Custom material *'), { target: { value: 'Linen' } });
    selectMaterial('Cotton', 'Others');
    expect(screen.queryByLabelText('Custom material *')).not.toBeInTheDocument();
    submit(container);
    await waitFor(() => expect(mocks.createProduct).toHaveBeenCalledWith(expect.objectContaining({ fabric_composition: 'Cotton' })));
  });
  it('keeps material optional when no option is selected', async () => {
    const { container } = await mount();
    await fillProduct(container, 'single');
    submit(container);
    await waitFor(() => expect(mocks.createProduct).toHaveBeenCalledWith(expect.objectContaining({ fabric_composition: undefined })));
  });
  it('preserves a custom material draft when toggling back to Others', async () => {
    await mount();
    selectMaterial('Others');
    fireEvent.change(screen.getByLabelText('Custom material *'), { target: { value: 'Linen' } });
    selectMaterial('Silk', 'Others');
    selectMaterial('Others', 'Silk');
    expect(screen.getByLabelText('Custom material *')).toHaveValue('Linen');
  });
  it('does not overwrite stored custom material when saving the existing edit form', async () => {
    mocks.getVendorProduct.mockResolvedValue({ id: 'existing', title: 'Linen shirt', base_price: 100,
      fabric_composition: 'Linen', status: 'draft', total_stock: 2 });
    mocks.updateProduct.mockResolvedValue({});
    const { container } = render(<MemoryRouter initialEntries={['/vendor/products/existing/edit']}><Routes>
      <Route path="/vendor/products/:id/edit" element={<VendorProductEdit />} />
    </Routes></MemoryRouter>);
    await screen.findByDisplayValue('Linen shirt');
    submit(container);
    await waitFor(() => expect(mocks.updateProduct).toHaveBeenCalled());
    expect(mocks.updateProduct.mock.calls[0][1]).not.toHaveProperty('fabric_composition');
  });
});
