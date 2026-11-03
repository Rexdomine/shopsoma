import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import EditVariantModal from './EditVariantModal';
import type { Product, ProductVariant } from '../../types';

function createMadeToOrderProduct(): { product: Product; currentVariant: ProductVariant } {
  const blueVariant: ProductVariant = {
    id: 'var-blue',
    product_id: 'prod-abebi',
    color: 'Blue Hand-dyed',
    price: 188000,
    stock: 0,
    is_available: true,
  };
  const brownVariant: ProductVariant = {
    id: 'var-brown',
    product_id: 'prod-abebi',
    color: 'Brown Hand-dyed',
    price: 188000,
    stock: 0,
    is_available: true,
  };

  const product: Product = {
    id: 'prod-abebi',
    vendor_id: 'vendor-pettre',
    title: 'Abebi Top',
    base_price: 188000,
    currency: 'NGN',
    status: 'active',
    product_type: 'variable',
    inventory_quantity: 0,
    total_stock: 0,
    made_to_order: true,
    made_to_order_timeline: '2 weeks',
    is_featured: false,
    moderation_status: 'approved',
    views_count: 0,
    orders_count: 0,
    variants: [blueVariant, brownVariant],
    images: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };

  return { product, currentVariant: blueVariant };
}

describe('EditVariantModal', () => {
  it('displays Made to Order instead of Out of stock and allows updating variants when stock is 0', () => {
    const { product, currentVariant } = createMadeToOrderProduct();
    const onClose = vi.fn();
    const onSave = vi.fn();

    render(
      <EditVariantModal
        open={true}
        product={product}
        currentVariant={currentVariant}
        onClose={onClose}
        onSave={onSave}
      />
    );

    expect(screen.getByText('Made to Order • 2 weeks')).toBeInTheDocument();
    expect(screen.queryByText(/out of stock/i)).not.toBeInTheDocument();

    const noChangesButton = screen.getByRole('button', { name: 'No Changes' });
    expect(noChangesButton).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Select color Brown Hand-dyed' }));

    const updateButton = screen.getByRole('button', { name: 'Update Variant' });
    expect(updateButton).toBeEnabled();

    fireEvent.click(updateButton);

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'var-brown',
        color: 'Brown Hand-dyed',
      })
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('still displays Out of stock and disables update for non-made-to-order variants with 0 stock', () => {
    const { product, currentVariant } = createMadeToOrderProduct();
    const rtwProduct: Product = {
      ...product,
      made_to_order: false,
      made_to_order_timeline: undefined,
    };

    render(
      <EditVariantModal
        open={true}
        product={rtwProduct}
        currentVariant={currentVariant}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );

    expect(screen.getByText('Out of stock')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Select color Brown Hand-dyed' }));

    const outOfStockButton = screen.getByRole('button', { name: 'Out of Stock' });
    expect(outOfStockButton).toBeDisabled();
  });
});
