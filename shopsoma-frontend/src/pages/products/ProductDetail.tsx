import { useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Heart, Minus, Plus, X } from 'lucide-react';
import type { Product, ProductVariant } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../../components/common/Loading';
import ProductCard from '../../components/products/ProductCard';
import { IMAGE_CONFIG } from '../../config/constants';
import Layout from '../../components/layout/Layout';
import AddToBagModal from '../../components/modals/AddToBagModal';
import { useCartStore } from '../../store/cartStore';

type ColorOption = {
  label: string;
  value: string;
  hex?: string | null;
};

export default function ProductDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const addItem = useCartStore((state) => state.addItem);

  const [product, setProduct] = useState<Product | null>(null);
  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string | null>(null);
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [wishlist, setWishlist] = useState(false);
  const [sizeGuideOpen, setSizeGuideOpen] = useState(false);
  const [sizeMenuOpen, setSizeMenuOpen] = useState(false);
  const [bagModalOpen, setBagModalOpen] = useState(false);
  const [addedVariant, setAddedVariant] = useState<ProductVariant | null>(null);
  const sizeDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) {
      navigate('/');
      return;
    }

    const fetchProduct = async () => {
      try {
        setLoading(true);
        const data = await productService.getProduct(id);
        setProduct(data);
        setSelectedImage(data.images?.[0]?.image_url ?? null);

        // Reset selections when product changes
        setSelectedColor(null);
        setSelectedSize(null);
        setQuantity(1);

        // Auto-select color/size if only one option
        const uniqueColors = getColorOptions(data.variants ?? []);
        if (uniqueColors.length === 1) {
          setSelectedColor(uniqueColors[0].value);
        }
        const uniqueSizes = getSizeOptions(data.variants ?? []);
        if (uniqueSizes.length === 1) {
          setSelectedSize(uniqueSizes[0]);
        }

        loadRelatedProducts(data.vendor_id, data.id);
      } catch (err) {
        console.error(err);
        setError('Product not found.');
      } finally {
        setLoading(false);
      }
    };

    fetchProduct();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadRelatedProducts = async (vendorId: string, currentProductId: string) => {
    try {
      const response = await productService.getProducts({
        vendor_id: vendorId,
        page_size: 4,
      });
      const filtered = response.products.filter((item) => item.id !== currentProductId);
      setRelatedProducts(filtered.slice(0, 4));
    } catch (err) {
      console.error('Failed to load related products', err);
    }
  };

  const getColorOptions = (variants: ProductVariant[]): ColorOption[] => {
    const uniqueMap = new Map<string, ColorOption>();
    variants.forEach((variant) => {
      if (variant.color) {
        const key = variant.color.toLowerCase();
        if (!uniqueMap.has(key)) {
          uniqueMap.set(key, {
            label: variant.color,
            value: variant.color,
            hex: variant.color_hex ?? null,
          });
        }
      }
    });
    return Array.from(uniqueMap.values());
  };

  const getSizeOptions = (variants: ProductVariant[]): string[] => {
    const set = new Set<string>();
    variants.forEach((variant) => {
      if (variant.size) {
        set.add(variant.size);
      }
    });
    return Array.from(set);
  };

  const colorOptions = useMemo(
    () => getColorOptions(product?.variants ?? []),
    [product?.variants]
  );
  const sizeOptions = useMemo(
    () => getSizeOptions(product?.variants ?? []),
    [product?.variants]
  );

  const selectedVariant = useMemo(() => {
    if (!product?.variants?.length) return null;

    let variants = product.variants;

    if (colorOptions.length && selectedColor) {
      variants = variants.filter(
        (variant) => variant.color?.toLowerCase() === selectedColor.toLowerCase()
      );
    }

    if (sizeOptions.length && selectedSize) {
      variants = variants.filter(
        (variant) => variant.size?.toLowerCase() === selectedSize.toLowerCase()
      );
    }

    return variants[0] ?? null;
  }, [product?.variants, colorOptions.length, sizeOptions.length, selectedColor, selectedSize]);

  const currentPrice =
    selectedVariant?.price ?? product?.base_price ?? 0;
  const comparePrice =
    selectedVariant?.compare_at_price ?? product?.compare_at_price ?? null;

  const maxQuantity = selectedVariant?.stock ?? product?.total_stock ?? 99;

  const handleQuantityChange = (direction: 'increment' | 'decrement') => {
    if (direction === 'increment') {
      setQuantity((prev) => Math.min(prev + 1, maxQuantity));
    } else {
      setQuantity((prev) => Math.max(prev - 1, 1));
    }
  };

  const handleAddToBag = () => {
    if (missingSelection || !product || !selectedVariant) return;

    // Add to cart using Zustand store
    addItem({
      product,
      variant: selectedVariant,
      quantity,
    });

    setAddedVariant(selectedVariant);
    setBagModalOpen(true);
  };

  const missingSelection =
    (colorOptions.length > 0 && !selectedColor) ||
    (sizeOptions.length > 0 && !selectedSize);

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;
  const galleryImages = product?.images ?? [];
  const sizeGuideRows = product?.size_guide?.rows ?? [];
  const hasSizeGuide = sizeGuideRows.length > 0;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        sizeMenuOpen &&
        sizeDropdownRef.current &&
        !sizeDropdownRef.current.contains(event.target as Node)
      ) {
        setSizeMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [sizeMenuOpen]);

  useEffect(() => {
    if (!hasSizeGuide && sizeGuideOpen) {
      setSizeGuideOpen(false);
    }
  }, [hasSizeGuide, sizeGuideOpen]);

  if (loading) {
    return (
      <div className="py-24">
        <Loading fullScreen message="Loading product..." />
      </div>
    );
  }

  if (error || !product) {
    return (
      <section className="py-24">
        <div className="max-w-4xl mx-auto px-4">
          <div className="text-center text-red-500">{error ?? 'Product not found.'}</div>
        </div>
      </section>
    );
  }

  const heroImage = selectedImage ?? galleryImages[0]?.image_url ?? placeholderImage;

  return (
    <Layout>
    <section className="bg-white py-12 lg:py-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="text-xs uppercase tracking-[0.3em] text-gray-400 mb-10">
          Home / Collection /{' '}
          <span className="text-gray-700">{product.category ?? 'Lifestyle'}</span>
        </nav>

        <div className="grid grid-cols-1 lg:grid-cols-[55%_45%] gap-12">
          {/* Gallery */}
          <div className="space-y-4">
            <div className="overflow-hidden bg-[#f5f7f8] aspect-[5/6] border border-gray-200 max-w-[560px] mx-auto">
              <img
                src={heroImage}
                alt={product.title}
                className="w-full h-full object-cover"
                onError={(event) => {
                  event.currentTarget.src = placeholderImage;
                  event.currentTarget.onerror = null;
                }}
              />
            </div>
            {galleryImages.length > 1 && (
              <div className="grid grid-cols-4 gap-3">
                {galleryImages.slice(0, 8).map((image) => (
                  <button
                    key={image.id}
                    type="button"
                    onClick={() => setSelectedImage(image.image_url)}
                    className={`overflow-hidden border-2 transition-all duration-200 aspect-square ${
                      selectedImage === image.image_url
                        ? 'border-primary'
                        : 'border-gray-200 hover:border-gray-400'
                    }`}
                  >
                    <img
                      src={image.image_url}
                      alt={image.alt_text ?? product.title}
                      className="w-full h-full object-cover"
                      onError={(event) => {
                        event.currentTarget.src = placeholderImage;
                        event.currentTarget.onerror = null;
                      }}
                    />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Product Info */}
          <div className="space-y-6">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Golden Editions</p>
              <h1 className="text-3xl font-display font-bold text-dark">{product.title}</h1>
              <p className="text-sm text-gray-500">{product.category ?? 'Collection'}</p>
            </div>

            <div>
              <div className="flex items-end gap-3">
                <span className="text-2xl font-semibold text-dark">
                  ₦{Number(currentPrice).toLocaleString()}
                </span>
                {comparePrice && comparePrice > currentPrice && (
                  <span className="text-base text-gray-400 line-through">
                    ₦{Number(comparePrice).toLocaleString()}
                  </span>
                )}
              </div>
            </div>

            {/* Color Selection */}
            {colorOptions.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Color</p>
                <div className="flex gap-3 flex-wrap">
                  {colorOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setSelectedColor(option.value)}
                      className={`w-11 h-11 rounded-full border-2 transition-all ${
                        selectedColor === option.value
                          ? 'border-primary ring-2 ring-primary/20'
                          : 'border-gray-300 hover:border-primary/60'
                      }`}
                      style={{
                        backgroundColor: option.hex ?? '#f5f5f5',
                      }}
                      aria-label={`Select color ${option.label}`}
                    />
                  ))}
                </div>
                {selectedColor && (
                  <p className="text-xs text-gray-600">Selected: {selectedColor}</p>
                )}
              </div>
            )}

            {/* Size Selection */}
            {sizeOptions.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-[0.3em] text-gray-400">
                  Size
                </div>
                <div className="relative" ref={sizeDropdownRef}>
                  <button
                    type="button"
                    className={`relative w-full px-4 py-3 pr-12 text-sm font-semibold text-left text-gray-700 bg-white transition cursor-pointer flex items-center justify-between focus:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/10 ${
                      sizeMenuOpen
                        ? 'border-2 border-primary ring-2 ring-primary/10'
                        : 'border border-gray-200 hover:border-primary/60'
                    }`}
                    onClick={() => setSizeMenuOpen((prev) => !prev)}
                  >
                    <span>{selectedSize ?? 'Select size'}</span>
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                      className={`pointer-events-none text-primary transition-transform absolute right-5 sm:right-6 top-1/2 -translate-y-1/2 ${
                        sizeMenuOpen ? 'rotate-180' : ''
                      }`}
                    >
                      <path
                        d="M6 9l6 6 6-6"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                  {sizeMenuOpen && (
                    <div className="absolute z-20 mt-2 w-full border border-gray-200 bg-white shadow-lg overflow-hidden">
                      {sizeOptions.map((size) => (
                        <button
                          key={size}
                          type="button"
                          onClick={() => {
                            setSelectedSize(size);
                            setSizeMenuOpen(false);
                          }}
                          className={`w-full text-left px-4 py-3 text-sm font-semibold transition ${
                            selectedSize === size
                              ? 'bg-primary/10 text-primary'
                              : 'text-gray-700 hover:bg-gray-50'
                          }`}
                        >
                          {size}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Quantity */}
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Quantity</p>
              <div className="inline-flex items-center border border-gray-200">
                <button
                  type="button"
                  className="px-4 py-2 text-gray-500 hover:text-primary transition"
                  onClick={() => handleQuantityChange('decrement')}
                >
                  <Minus className="w-4 h-4" />
                </button>
                <div className="px-6 py-2 font-semibold text-dark">{quantity}</div>
                <button
                  type="button"
                  className="px-4 py-2 text-gray-500 hover:text-primary transition"
                  onClick={() => handleQuantityChange('increment')}
                  disabled={quantity >= maxQuantity}
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              <p className="text-xs text-gray-400">
                {maxQuantity} pieces available
              </p>
            </div>

            <div className="flex flex-col lg:flex-row flex-wrap gap-3">
              <button
                type="button"
                disabled={missingSelection}
                className={`flex-1 border px-6 py-3 text-sm font-semibold transition-colors ${
                  missingSelection
                    ? 'bg-gray-100 text-gray-400 border-gray-100 cursor-not-allowed'
                    : 'bg-primary text-white hover:bg-primary-dark border-primary'
                }`}
                onClick={handleAddToBag}
              >
                Add to Bag
              </button>
              <button
                type="button"
                className={`border px-6 py-3 text-sm font-semibold flex items-center justify-center gap-2 transition-colors ${
                  wishlist ? 'border-primary text-primary' : 'border-gray-200 text-gray-700 hover:border-primary hover:text-primary'
                }`}
                onClick={() => setWishlist((prev) => !prev)}
              >
                Wishlist
                <Heart className={`w-4 h-4 ${wishlist ? 'fill-current text-primary' : ''}`} />
              </button>
              {hasSizeGuide && (
                <button
                  type="button"
                  className="border border-gray-200 px-6 py-3 text-sm font-semibold text-gray-700 hover:border-primary hover:text-primary transition-colors"
                  onClick={() => setSizeGuideOpen(true)}
                >
                  Size Guide
                </button>
              )}
            </div>

            {/* Details */}
            <div className="border-t border-gray-200 pt-6 space-y-4">
              <details className="group">
                <summary className="flex items-center justify-between cursor-pointer text-sm font-semibold text-dark">
                  Editor&apos;s Notes
                  <span className="text-primary group-open:rotate-45 transition-transform text-lg leading-none">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm text-gray-600 leading-relaxed">
                  {product.description ??
                    'Thoughtfully designed piece crafted with premium materials to elevate every wardrobe.'}
                </p>
              </details>

              <details className="group">
                <summary className="flex items-center justify-between cursor-pointer text-sm font-semibold text-dark">
                  Size &amp; Fit
                  <span className="text-primary group-open:rotate-45 transition-transform text-lg leading-none">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm text-gray-600 leading-relaxed">
                  True to size. We recommend selecting your usual size. Model wears size M.
                </p>
              </details>

              <details className="group">
                <summary className="flex items-center justify-between cursor-pointer text-sm font-semibold text-dark">
                  Shipping &amp; Returns
                  <span className="text-primary group-open:rotate-45 transition-transform text-lg leading-none">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm text-gray-600 leading-relaxed">
                  Complimentary delivery on orders over ₦30,000. Free returns within 7 days of
                  delivery for unused items.
                </p>
              </details>
            </div>
          </div>
        </div>

        {/* Related */}
        {relatedProducts.length > 0 && (
          <div className="mt-20">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-display font-semibold text-dark tracking-wide">
                Shop the Style
              </h2>
              <a
                href="/products"
                className="text-sm text-primary font-semibold hover:underline"
              >
                View all products
              </a>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {relatedProducts.map((related) => (
                <ProductCard product={related} key={related.id} />
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
      {/* Size Guide Modal */}
      {sizeGuideOpen && hasSizeGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white w-full max-w-2xl rounded-3xl shadow-2xl p-6 sm:p-10 relative">
            <button
              type="button"
              onClick={() => setSizeGuideOpen(false)}
              className="absolute top-6 right-6 text-gray-500 hover:text-dark"
              aria-label="Close size guide"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="grid grid-cols-1 sm:grid-cols-[120px_auto] gap-6 mb-6">
              <div className="rounded-2xl bg-gray-100 overflow-hidden aspect-[3/4]">
                <img
                  src={heroImage}
                  alt={product.title}
                  className="w-full h-full object-cover"
                  onError={(event) => {
                    event.currentTarget.src = placeholderImage;
                    event.currentTarget.onerror = null;
                  }}
                />
              </div>
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.3em] text-gray-400">
                  {product.size_guide?.gender || 'Size Guide'}
                </p>
                <h3 className="text-2xl font-display font-bold text-dark">
                  {product.size_guide?.title || product.title}
                </h3>
                <p className="text-sm text-gray-500">
                  {product.size_guide?.subtitle || product.category || 'Collection'}
                </p>
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm font-semibold text-gray-600 border-b pb-2">
                <span>Conversion Chart</span>
                <span>Inches / CM</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="uppercase text-xs tracking-[0.3em] text-gray-400">
                      <th className="py-3">Size</th>
                      <th className="py-3">Standard</th>
                      <th className="py-3">Measurement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sizeGuideRows.length
                      ? sizeGuideRows.map((row) => (
                          <tr key={row.label} className="border-t text-gray-700">
                            <td className="py-3 font-semibold">{row.label}</td>
                            <td className="py-3 uppercase">{row.standard ?? '—'}</td>
                            <td className="py-3">{row.measurement ?? '—'}</td>
                          </tr>
                        ))
                      : (
                        <tr className="border-t text-gray-500">
                          <td className="py-6" colSpan={3}>
                            No size guide available for this product yet.
                          </td>
                        </tr>
                      )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
      <AddToBagModal
        open={bagModalOpen}
        product={product}
        variant={addedVariant ?? selectedVariant}
        quantity={quantity}
        recommendations={relatedProducts}
        onClose={() => setBagModalOpen(false)}
      />
    </Layout>
  );
}
