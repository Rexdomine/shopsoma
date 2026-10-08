import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import VendorProductAdd from './VendorProductAdd';

const mocks = vi.hoisted(() => ({
  createProduct: vi.fn(),
  uploadImage: vi.fn(),
  getVendorProduct: vi.fn(),
  updateProduct: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  hideToast: vi.fn(),
}));

vi.mock('../../services/productService', () => ({ productService: mocks }));
vi.mock('../../services/categoryService', () => ({
  categoryService: {
    getPrimaryCategories: async () => [{ id: 'women', name: 'Women' }],
    getSubcategories: async () => [],
  },
}));
vi.mock('../../services/collectionService', () => ({
  collectionService: { getCollections: async () => [] },
}));
vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({ ...mocks, toasts: [] }),
}));
vi.mock('../../components/vendor/VendorSidebar', () => ({ default: () => null }));
vi.mock('../../components/vendor/CollectionModal', () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:preview'),
      revokeObjectURL: vi.fn(),
    })
  );
  mocks.uploadImage.mockResolvedValue({ original: 'https://example.test/linen.jpg' });
  mocks.createProduct.mockResolvedValue({ id: 'new' });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mount() {
  const result = render(
    <MemoryRouter>
      <VendorProductAdd />
    </MemoryRouter>
  );
  fireEvent.click(screen.getByRole('button', { name: 'Select category' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Women' }));
  return result;
}

function submit(container: HTMLElement) {
  fireEvent.submit(container.querySelector('form')!);
}

describe('VendorProductAdd price formatting and humanization', () => {
  it('formats product price and sales price with commas in the input while typing', async () => {
    await mount();

    const priceInputs = screen.getAllByPlaceholderText('0.00');
    const productPriceInput = priceInputs[0] as HTMLInputElement;
    const salesPriceInput = priceInputs[1] as HTMLInputElement;

    // Type 5000 into product price
    fireEvent.change(productPriceInput, { target: { value: '5000' } });
    expect(productPriceInput.value).toBe('5,000');

    // Type 50000 into product price
    fireEvent.change(productPriceInput, { target: { value: '5,0000' } });
    expect(productPriceInput.value).toBe('50,000');

    // Type 500000 into product price
    fireEvent.change(productPriceInput, { target: { value: '50,0000' } });
    expect(productPriceInput.value).toBe('500,000');

    // Type decimal into product price
    fireEvent.change(productPriceInput, { target: { value: '500,000.50' } });
    expect(productPriceInput.value).toBe('500,000.50');

    // Type into sales price
    fireEvent.change(salesPriceInput, { target: { value: '450000' } });
    expect(salesPriceInput.value).toBe('450,000');
  });

  it('submits pure numbers without commas to the backend when product is created', async () => {
    const { container } = await mount();

    // Fill required product info
    fireEvent.change(screen.getByPlaceholderText('Enter product name'), {
      target: { value: 'Silk Robe' },
    });
    fireEvent.change(screen.getByPlaceholderText('Describe your product'), {
      target: { value: 'A luxury silk robe' },
    });

    const priceInputs = screen.getAllByPlaceholderText('0.00');
    const productPriceInput = priceInputs[0] as HTMLInputElement;
    const salesPriceInput = priceInputs[1] as HTMLInputElement;

    // Type 75000 (regular price) and 60000 (sale price)
    fireEvent.change(productPriceInput, { target: { value: '75000' } });
    expect(productPriceInput.value).toBe('75,000');

    fireEvent.change(salesPriceInput, { target: { value: '60000' } });
    expect(salesPriceInput.value).toBe('60,000');

    // Shipping details
    for (const label of ['Weight (kg)', 'Length (cm)', 'Width (cm)', 'Height (cm)']) {
      fireEvent.change(
        screen.getByText(`${label} *`).parentElement!.querySelector('input')!,
        { target: { value: '1' } }
      );
    }

    // Color and size
    fireEvent.change(screen.getByPlaceholderText('E.g., Black'), {
      target: { value: 'Navy' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'M' }));

    // Image
    const inputs = container.querySelectorAll('input[type="file"]');
    fireEvent.change(inputs[inputs.length - 1], {
      target: { files: [new File(['image'], 'silk.jpg', { type: 'image/jpeg' })] },
    });
    await waitFor(() =>
      expect(container.querySelector('img[src="blob:preview"]')).not.toBeNull()
    );

    // Submit form
    submit(container);

    // Verify backend payload has NUMBERS without commas:
    // base_price should be 60000 (the active sale price)
    // compare_at_price should be 75000 (the regular price)
    await waitFor(() => {
      expect(mocks.createProduct).toHaveBeenCalledWith(
        expect.objectContaining({
          base_price: 60000,
          compare_at_price: 75000,
        })
      );
    });

    // Verify payload values are strictly typeof 'number' and contain no commas
    const callPayload = mocks.createProduct.mock.calls[0][0];
    expect(typeof callPayload.base_price).toBe('number');
    expect(callPayload.base_price).toBe(60000);
    expect(typeof callPayload.compare_at_price).toBe('number');
    expect(callPayload.compare_at_price).toBe(75000);
  });
});
