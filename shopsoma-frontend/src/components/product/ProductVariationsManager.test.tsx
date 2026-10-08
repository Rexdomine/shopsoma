import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductVariationsManager from './ProductVariationsManager';
import { productService } from '../../services/productService';
import { adminService } from '../../services/adminService';
import type { Variation, ProductImage } from '../../types';

vi.mock('../../services/productService', () => ({
  productService: {
    getVariations: vi.fn(),
    updateVariation: vi.fn(),
    deleteVariation: vi.fn(),
    uploadImage: vi.fn(),
    addProductImage: vi.fn(),
  },
}));

vi.mock('../../services/adminService', () => ({
  adminService: {
    getProductVariations: vi.fn(),
    updateProductVariation: vi.fn(),
    deleteProductVariation: vi.fn(),
  },
}));

const mockVariations: Variation[] = [
  {
    id: 'var-uuid-red',
    product_id: 'prod-123',
    title: 'Red',
    type: 'color',
    color_hex: '#FF0000',
    price: 55,
    sale_price: 45,
    inherits_price: false,
    inherits_sale_price: false,
    is_active: true,
    images: ['https://example.com/red1.jpg'],
    size_stocks: [
      { id: 'stock-1', variation_id: 'var-uuid-red', size: 'S', stock: 10 },
      { id: 'stock-2', variation_id: 'var-uuid-red', size: 'M', stock: 15 },
    ],
  },
  {
    id: 'var-uuid-blue',
    product_id: 'prod-123',
    title: 'Blue',
    type: 'color',
    color_hex: '#0000FF',
    price: 50,
    inherits_price: true,
    inherits_sale_price: true,
    is_active: false,
    images: ['https://example.com/blue1.jpg'],
    size_stocks: [
      { id: 'stock-3', variation_id: 'var-uuid-blue', size: 'L', stock: 8 },
    ],
  },
];

const mockProductImages: ProductImage[] = [
  {
    id: 'img-1',
    product_id: 'prod-123',
    image_url: 'https://example.com/red1.jpg',
    thumbnail_url: 'https://example.com/red1-thumb.jpg',
    display_order: 0,
    is_primary: true,
  },
  {
    id: 'img-2',
    product_id: 'prod-123',
    image_url: 'https://example.com/blue1.jpg',
    thumbnail_url: 'https://example.com/blue1-thumb.jpg',
    display_order: 1,
    is_primary: false,
  },
  {
    id: 'img-3',
    product_id: 'prod-123',
    image_url: 'https://example.com/extra.jpg',
    thumbnail_url: 'https://example.com/extra-thumb.jpg',
    display_order: 2,
    is_primary: false,
  },
];

describe('ProductVariationsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders every variation with unambiguous identity and badges', () => {
    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        currency="NGN"
        isAdmin={false}
      />
    );

    // List header and titles
    expect(screen.getByText('Product Variations')).toBeInTheDocument();
    expect(screen.getByText('Red')).toBeInTheDocument();
    expect(screen.getByText('Blue')).toBeInTheDocument();

    // Stable ID indicators
    expect(screen.getAllByText(/ID: var-uuid/i).length).toBe(2);

    // Status badges
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();

    // Sizes badges
    expect(screen.getByText('S:')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('M:')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('L:')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();

    // Stock totals
    expect(screen.getByText(/Total Stock: 25/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Stock: 8/i)).toBeInTheDocument();
  });

  it('enters selected-variation editing state with stable ID preserved', () => {
    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        currency="NGN"
        isAdmin={false}
      />
    );

    // Click Edit on Red variation
    const editBtn = screen.getByTestId('edit-variation-var-uuid-red');
    fireEvent.click(editBtn);

    // Verify in selected-variation editing view
    expect(screen.getByTestId('selected-variation-editor')).toBeInTheDocument();
    expect(screen.getByText(/Editing Variation:/i)).toBeInTheDocument();
    expect(screen.getByText(/Stable ID: var-uuid-red/i)).toBeInTheDocument();

    // Inputs prefilled
    const titleInput = screen.getByLabelText(/Variation Title/i) as HTMLInputElement;
    expect(titleInput.value).toBe('Red');

    const colorHexInput = screen.getByPlaceholderText('#FFFFFF') as HTMLInputElement;
    expect(colorHexInput.value).toBe('#FF0000');

    // Canceling exits editor back to list
    fireEvent.click(screen.getAllByRole('button', { name: 'Cancel' })[0]);
    expect(screen.queryByTestId('selected-variation-editor')).not.toBeInTheDocument();
    expect(screen.getByText('Product Variations')).toBeInTheDocument();
  });

  it('allows editing title, color hex, price overrides, and saves changes via vendor service', async () => {
    const onUpdatedMock = vi.fn();
    const updatedResponse: Variation = {
      ...mockVariations[0],
      title: 'Crimson Red',
      color_hex: '#DC143C',
      price: 60,
    };
    (productService.updateVariation as any).mockResolvedValueOnce(updatedResponse);

    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        currency="NGN"
        isAdmin={false}
        onVariationsUpdated={onUpdatedMock}
      />
    );

    // Enter editing state
    fireEvent.click(screen.getByTestId('edit-variation-var-uuid-red'));

    // Edit title
    const titleInput = screen.getByLabelText(/Variation Title/i);
    fireEvent.change(titleInput, { target: { value: 'Crimson Red' } });

    // Edit color hex
    const colorHexInput = screen.getByPlaceholderText('#FFFFFF');
    fireEvent.change(colorHexInput, { target: { value: '#DC143C' } });

    // Edit custom price
    const priceInput = screen.getByPlaceholderText('Enter custom regular price');
    fireEvent.change(priceInput, { target: { value: '60' } });

    // Click Save
    const saveBtn = screen.getByRole('button', { name: /Save Variation Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(productService.updateVariation).toHaveBeenCalledWith(
        'prod-123',
        'var-uuid-red',
        expect.objectContaining({
          title: 'Crimson Red',
          color_hex: '#DC143C',
          price: 60,
          inherits_price: false,
        })
      );
    });

    expect(onUpdatedMock).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ title: 'Crimson Red', id: 'var-uuid-red' }),
        expect.objectContaining({ title: 'Blue', id: 'var-uuid-blue' }), // Untouched sibling preserved
      ])
    );
  });

  it('admin uses adminService.updateProductVariation when isAdmin=true', async () => {
    const updatedResponse: Variation = {
      ...mockVariations[0],
      title: 'Admin Curated Red',
    };
    (adminService.updateProductVariation as any).mockResolvedValueOnce(updatedResponse);

    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        currency="NGN"
        isAdmin={true}
      />
    );

    fireEvent.click(screen.getByTestId('edit-variation-var-uuid-red'));

    const titleInput = screen.getByLabelText(/Variation Title/i);
    fireEvent.change(titleInput, { target: { value: 'Admin Curated Red' } });

    fireEvent.click(screen.getByRole('button', { name: /Save Variation Changes/i }));

    await waitFor(() => {
      expect(adminService.updateProductVariation).toHaveBeenCalledWith(
        'prod-123',
        'var-uuid-red',
        expect.objectContaining({
          title: 'Admin Curated Red',
        })
      );
    });
  });

  it('manages nested size stocks: adding and removing sizes', () => {
    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        isAdmin={false}
      />
    );

    fireEvent.click(screen.getByTestId('edit-variation-var-uuid-red'));

    // Existing sizes S (10) and M (15) are shown
    expect(screen.getByText('S', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText('M', { selector: 'span' })).toBeInTheDocument();

    // Add size XL with stock 12
    const sizeSelect = screen.getByLabelText(/^Size$/i);
    fireEvent.change(sizeSelect, { target: { value: 'XL' } });

    const stockInput = screen.getByLabelText(/Stock Quantity/i);
    fireEvent.change(stockInput, { target: { value: '12' } });

    fireEvent.click(screen.getByRole('button', { name: /Add Size/i }));

    expect(screen.getByText('XL', { selector: 'span' })).toBeInTheDocument();

    // Remove size M
    const removeMBtn = screen.getByLabelText('Remove size M');
    fireEvent.click(removeMBtn);

    expect(screen.queryByText('M', { selector: 'span' })).not.toBeInTheDocument();
  });

  it('scopes variation images: selects from product gallery without modifying parent gallery', () => {
    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        isAdmin={false}
      />
    );

    fireEvent.click(screen.getByTestId('edit-variation-var-uuid-red'));

    // Open image picker
    fireEvent.click(screen.getByRole('button', { name: /Select from Product Images/i }));

    // Product gallery images shown
    expect(screen.getByText('Select Variation Images')).toBeInTheDocument();

    // Click third image to add it
    const images = screen.getAllByAltText('Product option');
    expect(images.length).toBe(3);
    fireEvent.click(images[2]);

    // Close picker
    fireEvent.click(screen.getByRole('button', { name: /Done/i }));

    // Selected images now includes the newly selected one
    expect(screen.getAllByAltText(/Variation/i).length).toBe(2);

    // Remove an image from variation
    const removeImgBtn = screen.getAllByLabelText('Remove image from variation')[0];
    fireEvent.click(removeImgBtn);

    expect(screen.getAllByAltText(/Variation/i).length).toBe(1);
  });

  it('deletes variation after confirmation and notifies parent', async () => {
    const onUpdatedMock = vi.fn();
    (productService.deleteVariation as any).mockResolvedValueOnce(undefined);

    render(
      <ProductVariationsManager
        productId="prod-123"
        initialVariations={mockVariations}
        productImages={mockProductImages}
        basePrice={50}
        isAdmin={false}
        onVariationsUpdated={onUpdatedMock}
      />
    );

    // Click delete on Blue variation
    const deleteBtn = screen.getByTestId('delete-variation-var-uuid-blue');
    fireEvent.click(deleteBtn);

    // Confirmation modal appears
    expect(screen.getByText(/Are you sure you want to delete the variation/i)).toBeInTheDocument();
    expect(screen.getByText(/"Blue"/i)).toBeInTheDocument();

    // Confirm delete
    const confirmDeleteBtn = screen.getByRole('button', { name: /^Delete$/i });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(productService.deleteVariation).toHaveBeenCalledWith('prod-123', 'var-uuid-blue');
    });

    expect(onUpdatedMock).toHaveBeenCalledWith(
      expect.not.arrayContaining([
        expect.objectContaining({ id: 'var-uuid-blue' }),
      ])
    );
  });
});
