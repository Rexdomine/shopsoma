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

async function mount() {
  const result = render(
    <MemoryRouter>
      <VendorProductAdd />
    </MemoryRouter>
  );

  // Select category
  fireEvent.click(screen.getByRole('button', { name: 'Select category' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Apparel' }));

  return result;
}

describe('VendorProductAdd Variable Product Combination Matrix', () => {
  it('allows adding combination variations and renders the Sellable Combinations Matrix', async () => {
    const { container } = await mount();

    // Fill common required fields
    fireEvent.change(screen.getByPlaceholderText('Enter product name'), {
      target: { value: 'Oxford Button Down' },
    });
    fireEvent.change(screen.getByPlaceholderText('Describe your product'), {
      target: { value: 'High quality linen oxford shirt.' },
    });

    const priceInputs = screen.getAllByPlaceholderText('0.00');
    fireEvent.change(priceInputs[0], { target: { value: '120' } });

    // Shipping parcel dimensions
    for (const label of ['Weight (kg)', 'Length (cm)', 'Width (cm)', 'Height (cm)']) {
      fireEvent.change(
        screen.getByText(`${label} *`).parentElement!.querySelector('input')!,
        { target: { value: '1' } }
      );
    }

    // Switch to Variable Product
    const variableButton = screen.getByRole('button', { name: 'Variable Product' });
    fireEvent.click(variableButton);

    expect(screen.getByText('Product Variations')).toBeInTheDocument();

    // Click "Add Variation"
    const addVariationButtons = screen.getAllByRole('button', { name: /Add Variation/i });
    fireEvent.click(addVariationButtons[0]);

    // Modal is open
    const modal = screen.getByRole('heading', { name: 'Add Variation' }).closest('div.fixed') as HTMLElement;
    expect(modal).toBeInTheDocument();

    // Combination mode is selected by default
    const typeSelect = within(modal).getByDisplayValue('Combination (Color + Sizes)') as HTMLSelectElement;
    expect(typeSelect.value).toBe('Combination');

    // Fill Color label inside modal
    const colorLabelInput = within(modal).getByPlaceholderText('E.g., Black');
    fireEvent.change(colorLabelInput, { target: { value: 'Midnight Black' } });

    // Select sizes S and M inside modal
    const sizeSButton = within(modal).getByRole('button', { name: 'S' });
    const sizeMButton = within(modal).getByRole('button', { name: 'M' });
    fireEvent.click(sizeSButton);
    fireEvent.click(sizeMButton);

    // Enter stock for S (10) and M (15)
    const sizeLabels = within(modal).getAllByText('S');
    const sizeSLabel = sizeLabels.find((el) => el.tagName === 'LABEL');
    const sizeSInput = sizeSLabel?.parentElement?.querySelector('input');
    if (sizeSInput) {
      fireEvent.change(sizeSInput, { target: { value: '10' } });
    }

    const mLabels = within(modal).getAllByText('M');
    const sizeMLabel = mLabels.find((el) => el.tagName === 'LABEL');
    const sizeMInput = sizeMLabel?.parentElement?.querySelector('input');
    if (sizeMInput) {
      fireEvent.change(sizeMInput, { target: { value: '15' } });
    }

    // Upload an image for this variation
    const fileInput = modal.querySelector('input[type="file"][accept*="image"]') as HTMLInputElement;
    const file = new File(['mock'], 'midnight-black.jpg', { type: 'image/jpeg' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(mocks.uploadImage).toHaveBeenCalled();
    });

    // Save variation
    fireEvent.click(within(modal).getByRole('button', { name: /Save Variation/i }));

    // Verify toast
    expect(mocks.success).toHaveBeenCalledWith('Variation saved');

    // Check that variation card and Sellable Combinations Matrix are rendered
    await waitFor(() => {
      expect(screen.getByText('Sellable Combinations Matrix')).toBeInTheDocument();
    });

    // Verify matrix rows: Midnight Black / S, Midnight Black / M
    expect(screen.getByText('Midnight Black / S')).toBeInTheDocument();
    expect(screen.getByText('Midnight Black / M')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();

    // Now submit product
    fireEvent.submit(container.querySelector('form')!);

    await waitFor(() => {
      expect(mocks.createProduct).toHaveBeenCalled();
    });

    const createPayload = mocks.createProduct.mock.calls[0][0];
    expect(createPayload.product_type).toBe('variable');
    expect(createPayload.total_stock).toBe(25); // 10 + 15
    expect(createPayload.variations).toHaveLength(1);
    expect(createPayload.variations[0].title).toBe('Midnight Black');
    expect(createPayload.variations[0].sizes).toEqual([
      { size: 'S', stock: 10 },
      { size: 'M', stock: 15 },
    ]);
    // Ensure legacy variants are NOT sent
    expect(createPayload.variants).toBeUndefined();
  });

  it('rejects duplicate variation labels with a clear warning', async () => {
    await mount();

    // Switch to Variable Product
    const variableButton = screen.getByRole('button', { name: 'Variable Product' });
    fireEvent.click(variableButton);

    // Add first variation: "Royal Blue"
    fireEvent.click(screen.getAllByRole('button', { name: /Add Variation/i })[0]);
    let modal = screen.getByRole('heading', { name: 'Add Variation' }).closest('div.fixed') as HTMLElement;
    fireEvent.change(within(modal).getByPlaceholderText('E.g., Black'), { target: { value: 'Royal Blue' } });
    fireEvent.click(within(modal).getByRole('button', { name: 'M' }));

    const fileInput = modal.querySelector('input[type="file"][accept*="image"]') as HTMLInputElement;
    const file = new File(['mock'], 'blue.jpg', { type: 'image/jpeg' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(mocks.uploadImage).toHaveBeenCalled();
    });

    fireEvent.click(within(modal).getByRole('button', { name: /Save Variation/i }));
    expect(mocks.success).toHaveBeenCalledWith('Variation saved');

    // Add second variation with the SAME label: "Royal Blue"
    fireEvent.click(screen.getByRole('button', { name: /Add Variation/i }));
    modal = screen.getByRole('heading', { name: 'Add Variation' }).closest('div.fixed') as HTMLElement;
    fireEvent.change(within(modal).getByPlaceholderText('E.g., Black'), { target: { value: 'Royal Blue' } });
    fireEvent.click(within(modal).getByRole('button', { name: 'L' }));

    const fileInput2 = modal.querySelector('input[type="file"][accept*="image"]') as HTMLInputElement;
    fireEvent.change(fileInput2, { target: { files: [file] } });

    await waitFor(() => {
      expect(mocks.uploadImage).toHaveBeenCalledTimes(2);
    });

    fireEvent.click(within(modal).getByRole('button', { name: /Save Variation/i }));

    // Should reject duplicate label
    expect(mocks.warning).toHaveBeenCalledWith(
      expect.stringContaining('already exists')
    );
  });
});
