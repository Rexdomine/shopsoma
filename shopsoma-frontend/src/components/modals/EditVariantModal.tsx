import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import type { Product, ProductVariant } from '../../types';
import { IMAGE_CONFIG } from '../../config/constants';

interface EditVariantModalProps {
  open: boolean;
  product: Product;
  currentVariant: ProductVariant;
  onClose: () => void;
  onSave: (newVariant: ProductVariant) => void;
}

export default function EditVariantModal({
  open,
  product,
  currentVariant,
  onClose,
  onSave,
}: EditVariantModalProps) {
  const [selectedSize, setSelectedSize] = useState(currentVariant.size);
  const [selectedColor, setSelectedColor] = useState(currentVariant.color);
  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(currentVariant);

  useEffect(() => {
    if (open) {
      setSelectedSize(currentVariant.size);
      setSelectedColor(currentVariant.color);
      setSelectedVariant(currentVariant);
    }
  }, [open, currentVariant]);

  // Extract unique sizes and colors from variants
  const availableSizes = Array.from(
    new Set(product.variants?.map((v) => v.size).filter(Boolean))
  );

  // Get unique colors with hex values
  const availableColors = (() => {
    const colorMap = new Map<string, { color: string; hex: string | null }>();
    product.variants?.forEach((v) => {
      if (v.color) {
        const key = v.color.toLowerCase();
        if (!colorMap.has(key)) {
          colorMap.set(key, { color: v.color, hex: v.color_hex ?? null });
        }
      }
    });
    return Array.from(colorMap.values());
  })();

  // Update selected variant when size or color changes
  useEffect(() => {
    if (!product.variants) return;

    const variant = product.variants.find(
      (v) => v.size === selectedSize && v.color === selectedColor
    );

    if (variant) {
      setSelectedVariant(variant);
    }
  }, [selectedSize, selectedColor, product.variants]);

  const handleSave = () => {
    if (selectedVariant) {
      onSave(selectedVariant);
      onClose();
    }
  };

  const isInStock = (selectedVariant?.stock ?? 0) > 0;
  const hasChanged = selectedVariant?.id !== currentVariant.id;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 py-8">
      <div className="relative w-full max-w-[500px] bg-white shadow-2xl overflow-hidden border border-gray-100">
        <button
          type="button"
          className="absolute top-6 right-6 text-gray-400 hover:text-dark"
          aria-label="Close"
          onClick={onClose}
        >
          <X className="w-5 h-5" />
        </button>

        <div className="p-6 sm:p-8 space-y-6">
          <div className="flex items-start gap-4">
            <div className="w-20 h-24 overflow-hidden bg-[#f5f7f8] border border-gray-200">
              <img
                src={product.images?.[0]?.image_url ?? IMAGE_CONFIG.PLACEHOLDER}
                alt={product.title}
                className="w-full h-full object-cover"
                onError={(event) => {
                  event.currentTarget.src = IMAGE_CONFIG.PLACEHOLDER;
                }}
              />
            </div>
            <div className="flex-1">
              <p className="text-xs uppercase tracking-[0.4em] text-gray-400 mb-1">
                Edit Variant
              </p>
              <h3 className="text-2xl font-display font-semibold text-dark">
                {product.title}
              </h3>
            </div>
          </div>

          {/* Size Selection */}
          {availableSizes.length > 0 && (
            <div className="space-y-3">
              <label className="block text-sm font-semibold uppercase tracking-[0.3em] text-gray-500">
                Size
              </label>
              <div className="flex flex-wrap gap-2">
                {availableSizes.map((size) => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => setSelectedSize(size)}
                    className={`px-6 py-2 border text-sm font-medium transition ${
                      selectedSize === size
                        ? 'border-primary bg-primary text-white'
                        : 'border-gray-300 text-gray-700 hover:border-primary'
                    }`}
                  >
                    {size}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Color Selection */}
          {availableColors.length > 0 && (
            <div className="space-y-3">
              <label className="block text-sm font-semibold uppercase tracking-[0.3em] text-gray-500">
                Color
              </label>
              <div className="flex flex-wrap gap-3">
                {availableColors.map((colorOption) => (
                  <button
                    key={colorOption.color}
                    type="button"
                    onClick={() => setSelectedColor(colorOption.color)}
                    className={`w-11 h-11 border-2 transition-all ${
                      selectedColor === colorOption.color
                        ? 'border-primary ring-2 ring-primary/20'
                        : 'border-gray-300 hover:border-primary/60'
                    }`}
                    style={{
                      backgroundColor: colorOption.hex ?? '#f5f5f5',
                    }}
                    aria-label={`Select color ${colorOption.color}`}
                    title={colorOption.color}
                  />
                ))}
              </div>
              {selectedColor && (
                <p className="text-xs text-gray-600">Selected: {selectedColor}</p>
              )}
            </div>
          )}

          {/* Variant Info */}
          <div className="bg-[#f5f7f8] p-4 space-y-2 border border-gray-200">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Price</span>
              <span className="font-semibold text-dark">
                ₦{Number(selectedVariant?.price ?? product.base_price).toLocaleString()}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Stock</span>
              <span className={`font-medium ${isInStock ? 'text-green-600' : 'text-red-600'}`}>
                {isInStock ? `${selectedVariant?.stock} available` : 'Out of stock'}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-gray-300 py-3 text-sm font-semibold text-gray-700 hover:border-primary hover:text-primary transition"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!isInStock || !hasChanged}
              className="flex-1 py-3 text-sm font-semibold text-white bg-primary hover:bg-primary-dark transition disabled:opacity-50 disabled:cursor-not-allowed border border-primary"
            >
              {!hasChanged ? 'No Changes' : !isInStock ? 'Out of Stock' : 'Update Variant'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
