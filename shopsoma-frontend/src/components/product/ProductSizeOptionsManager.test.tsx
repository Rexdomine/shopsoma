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
});
