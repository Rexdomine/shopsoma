import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductSizeOptionsManager from './ProductSizeOptionsManager';

const productMocks = vi.hoisted(() => ({
  getProductVariants: vi.fn(),
  createVariant: vi.fn(),
  updateVariant: vi.fn(),
  deleteVariant: vi.fn(),
}));

const adminMocks = vi.hoisted(() => ({
  getProductVariants: vi.fn(),
  createProductVariant: vi.fn(),
  updateProductVariant: vi.fn(),
  deleteProductVariant: vi.fn(),
}));

vi.mock('../../services/productService', () => ({
  productService: productMocks,
}));

vi.mock('../../services/adminService', () => ({
  adminService: adminMocks,
}));

describe('ProductSizeOptionsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sizing preset buttons with two-line layout so One / Size fits well', () => {
    render(
      <ProductSizeOptionsManager
        productId="p-1"
        initialVariants={[]}
        basePrice={50}
        isAdmin={false}
      />
    );

    // Open Add modal
    fireEvent.click(screen.getByRole('button', { name: /Add Size Option/i }));

    // Verify Sizing System Preset buttons
    expect(screen.getByText('US')).toBeInTheDocument();
    expect(screen.getByText('UK')).toBeInTheDocument();
    expect(screen.getByText('EU')).toBeInTheDocument();
    expect(screen.getByText('One /')).toBeInTheDocument();
    expect(screen.getByText('Custom')).toBeInTheDocument();
  });

  it('uses a dropdown for preset sizes and free text input only for custom size in Add modal', () => {
    render(
      <ProductSizeOptionsManager
        productId="p-1"
        initialVariants={[]}
        basePrice={50}
        isAdmin={false}
      />
    );

    // Open Add modal
    fireEvent.click(screen.getByRole('button', { name: /Add Size Option/i }));

    // Default preset is US Sizing: Size Label must be a dropdown (<select>)
    const selectDropdown = screen.getByRole('combobox');
    expect(selectDropdown).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'S' })).toBeInTheDocument();

    // Click "One / Size" preset tab
    fireEvent.click(screen.getByText('One /').closest('button')!);
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'One/Size' })).toBeInTheDocument();

    // Click "Custom" preset tab: now it should be a free text input (<input type="text">)
    fireEvent.click(screen.getByText('Custom').closest('button')!);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    const customTextInput = screen.getByPlaceholderText(/e\.g\. Tailored Fit/i);
    expect(customTextInput).toBeInTheDocument();
    expect(customTextInput.tagName).toBe('INPUT');
  });

  it('uses a dropdown for preset sizes and free text input only for custom size in Edit modal', () => {
    const mockVariants = [
      {
        id: 'var-1',
        product_id: 'p-1',
        size: 'M',
        stock: 5,
        price: 50,
        is_available: true,
      },
    ];

    render(
      <ProductSizeOptionsManager
        productId="p-1"
        initialVariants={mockVariants as any}
        basePrice={50}
        isAdmin={true}
      />
    );

    // Open Edit modal
    fireEvent.click(screen.getByRole('button', { name: /Edit size M/i }));

    // Should detect US Sizing and show dropdown for M
    const selectDropdown = screen.getByRole('combobox');
    expect(selectDropdown).toBeInTheDocument();
    expect((selectDropdown as HTMLSelectElement).value).toBe('M');

    // Switch to Custom size
    fireEvent.click(screen.getByText('Custom').closest('button')!);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    const customInput = screen.getByPlaceholderText(/e\.g\. Tailored Fit/i);
    expect(customInput).toBeInTheDocument();
  });

  it('saves edits to a variant without submitting a parent form, preserving existing color', async () => {
    const parentSubmitSpy = vi.fn((e) => e.preventDefault());
    const mockVariants = [
      {
        id: 'var-1',
        product_id: 'p-1',
        size: 'XS',
        color: 'Black',
        color_hex: '#000000',
        stock: 0,
        price: 23000,
        is_available: false,
      },
    ];

    productMocks.updateVariant.mockResolvedValueOnce({
      ...mockVariants[0],
      stock: 15,
      price: 25000,
      is_available: true,
    });
    productMocks.getProductVariants.mockResolvedValueOnce([
      {
        ...mockVariants[0],
        stock: 15,
        price: 25000,
        is_available: true,
      },
    ]);

    render(
      <form onSubmit={parentSubmitSpy}>
        <ProductSizeOptionsManager
          productId="p-1"
          initialVariants={mockVariants as any}
          basePrice={23000}
          isAdmin={false}
        />
      </form>
    );

    // Open Edit modal
    fireEvent.click(screen.getByRole('button', { name: /Edit size XS/i }));
    expect(screen.getByText('Edit Size Option')).toBeInTheDocument();

    // Change stock and price
    const stockInput = screen.getByLabelText(/Stock Quantity/i);
    fireEvent.change(stockInput, { target: { value: '15' } });

    const priceInput = screen.getByLabelText(/Price/i);
    fireEvent.change(priceInput, { target: { value: '25000' } });

    // Check availability
    const availableCheckbox = screen.getByLabelText(/Available for purchase/i);
    fireEvent.click(availableCheckbox);

    // Click Save Changes button
    const saveButton = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveButton);

    // Verify parent form was NOT submitted
    expect(parentSubmitSpy).not.toHaveBeenCalled();

    // Verify updateVariant was called with preserved color and updated values
    expect(productMocks.updateVariant).toHaveBeenCalledWith('p-1', 'var-1', {
      size: 'XS',
      color: 'Black',
      color_hex: '#000000',
      stock: 15,
      price: 25000,
      is_available: true,
    });
  });

  it('displays error message inside the modal when updateVariant fails', async () => {
    const mockVariants = [
      {
        id: 'var-1',
        product_id: 'p-1',
        size: 'XS',
        stock: 0,
        price: 23000,
        is_available: false,
      },
    ];

    productMocks.updateVariant.mockRejectedValueOnce({
      response: {
        data: {
          detail: 'Database validation failed for this size',
        },
      },
    });

    render(
      <ProductSizeOptionsManager
        productId="p-1"
        initialVariants={mockVariants as any}
        basePrice={23000}
        isAdmin={false}
      />
    );

    // Open Edit modal
    fireEvent.click(screen.getByRole('button', { name: /Edit size XS/i }));

    // Click Save Changes
    const saveButton = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveButton);

    // Error should be visible inside the modal
    expect(await screen.findByText('Database validation failed for this size')).toBeInTheDocument();
  });
});
