import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import VendorProductAdd from '../VendorProductAdd';

const mocks = vi.hoisted(() => ({
  createProduct: vi.fn(),
  uploadImage: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  hideToast: vi.fn(),
}));

vi.mock('../../../services/productService', () => ({ productService: mocks }));
vi.mock('../../../services/categoryService', () => ({
  categoryService: {
    getPrimaryCategories: async () => [{ id: 'apparel', name: 'Apparel' }],
    getSubcategories: async () => [],
  },
}));
vi.mock('../../../services/collectionService', () => ({
  collectionService: { getCollections: async () => [] },
}));
vi.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ ...mocks, toasts: [] }),
}));
vi.mock('../../../components/vendor/VendorSidebar', () => ({ default: () => null }));
vi.mock('../../../components/vendor/CollectionModal', () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:mock-image'),
      revokeObjectURL: vi.fn(),
    })
  );
  mocks.uploadImage.mockResolvedValue({
    original: 'https://cdn.shopsoma.test/black.jpg',
    thumbnail: 'https://cdn.shopsoma.test/black-thumb.jpg',
    storage_keys: ['black.jpg'],
  });
  mocks.createProduct.mockResolvedValue({ id: 'prod-123' });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mountWithBasics() {
  const result = render(
    <MemoryRouter>
      <VendorProductAdd />
    </MemoryRouter>
  );
  fireEvent.click(screen.getByRole('button', { name: 'Select category' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Apparel' }));
  fireEvent.change(screen.getByPlaceholderText('Enter product name'), {
    target: { value: 'Oxford Button Down' },
  });
  fireEvent.change(screen.getByPlaceholderText('Describe your product'), {
    target: { value: 'High quality linen oxford shirt.' },
  });
  fireEvent.change(screen.getAllByPlaceholderText('0.00')[0], { target: { value: '120' } });
  return result;
}

function parcelInput(label: string) {
  return screen.getByText(label).parentElement!.querySelector('input')!;
}

describe('VendorProductAdd optional shipping parcel details', () => {
  it('no longer advertises DHL as coming soon and marks parcel details optional', async () => {
    await mountWithBasics();

    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
    expect(screen.getByText('Optional')).toBeInTheDocument();
    for (const label of ['Weight (kg)', 'Length (cm)', 'Width (cm)', 'Height (cm)']) {
      expect(parcelInput(label)).not.toBeRequired();
    }
  });

  it('rejects a partially filled parcel before calling the API', async () => {
    const { container } = await mountWithBasics();
    fireEvent.change(parcelInput('Weight (kg)'), { target: { value: '1.2' } });

    fireEvent.submit(container.querySelector('form')!);

    expect(mocks.warning).toHaveBeenCalledWith(
      expect.stringContaining('leave all four blank'),
      'Incomplete parcel details'
    );
    expect(mocks.createProduct).not.toHaveBeenCalled();
  });

  it('creates the product without parcel fields when all four are left blank', async () => {
    const { container } = await mountWithBasics();

    fireEvent.click(screen.getByRole('button', { name: 'Variable Product' }));
    fireEvent.click(screen.getAllByRole('button', { name: /Add Variation/i })[0]);
    const modal = screen.getByRole('heading', { name: 'Add Variation' }).closest('div.fixed') as HTMLElement;
    fireEvent.change(within(modal).getByPlaceholderText('E.g., Black'), { target: { value: 'Midnight Black' } });
    fireEvent.click(within(modal).getByRole('button', { name: 'S' }));
    const fileInput = modal.querySelector('input[type="file"][accept*="image"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['mock'], 'black.jpg', { type: 'image/jpeg' })] } });
    await waitFor(() => expect(mocks.uploadImage).toHaveBeenCalled());
    fireEvent.click(within(modal).getByRole('button', { name: /Save Variation/i }));
    expect(mocks.success).toHaveBeenCalledWith('Variation saved');

    fireEvent.submit(container.querySelector('form')!);

    await waitFor(() => expect(mocks.createProduct).toHaveBeenCalled());
    const payload = mocks.createProduct.mock.calls[0][0];
    for (const key of ['weight_kg', 'length_cm', 'width_cm', 'height_cm']) {
      expect(payload).not.toHaveProperty(key);
    }
  });

  it('still sends all four measurements when the vendor provides them', async () => {
    const { container } = await mountWithBasics();
    for (const [label, value] of [['Weight (kg)', '1.2'], ['Length (cm)', '35'], ['Width (cm)', '25'], ['Height (cm)', '6']]) {
      fireEvent.change(parcelInput(label), { target: { value } });
    }

    fireEvent.click(screen.getByRole('button', { name: 'Variable Product' }));
    fireEvent.click(screen.getAllByRole('button', { name: /Add Variation/i })[0]);
    const modal = screen.getByRole('heading', { name: 'Add Variation' }).closest('div.fixed') as HTMLElement;
    fireEvent.change(within(modal).getByPlaceholderText('E.g., Black'), { target: { value: 'Midnight Black' } });
    fireEvent.click(within(modal).getByRole('button', { name: 'S' }));
    const fileInput = modal.querySelector('input[type="file"][accept*="image"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['mock'], 'black.jpg', { type: 'image/jpeg' })] } });
    await waitFor(() => expect(mocks.uploadImage).toHaveBeenCalled());
    fireEvent.click(within(modal).getByRole('button', { name: /Save Variation/i }));

    fireEvent.submit(container.querySelector('form')!);

    await waitFor(() => expect(mocks.createProduct).toHaveBeenCalled());
    expect(mocks.createProduct.mock.calls[0][0]).toMatchObject({
      weight_kg: 1.2,
      length_cm: 35,
      width_cm: 25,
      height_cm: 6,
    });
  });
});
