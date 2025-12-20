import { useEffect, useMemo, useState, useRef, type SVGProps } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Bookmark, Minus, Plus, X } from 'lucide-react';
import type { Product, ProductVariant, SizeGuide } from '../../types';
import { productService } from '../../services/productService';
import { wishlistService } from '../../services/wishlistService';
import Loading from '../../components/common/Loading';
import ProductCard from '../../components/products/ProductCard';
import { IMAGE_CONFIG, STORAGE_KEYS } from '../../config/constants';
import Layout from '../../components/layout/Layout';
import AddToBagModal from '../../components/modals/AddToBagModal';
import { useCartStore } from '../../store/cartStore';
import { formatPriceWithConversion, formatPriceWithCurrency } from '../../utils/pricing';
import { useCurrencyStore } from '../../store/currencyStore';

const FALLBACK_SIZE_GUIDE: SizeGuide = {
  gender: 'General Fit',
  title: 'Size Guidance',
  subtitle: 'Signature silhouettes',
  rows: [
    { label: 'XS', standard: 'US 2', measurement: 'Bust 32" / Waist 24" / Hips 35"' },
    { label: 'S', standard: 'US 4-6', measurement: 'Bust 34" / Waist 26" / Hips 37"' },
    { label: 'M', standard: 'US 8-10', measurement: 'Bust 36" / Waist 28" / Hips 39"' },
    { label: 'L', standard: 'US 12-14', measurement: 'Bust 39" / Waist 31" / Hips 42"' },
  ],
};

type ColorOption = {
  label: string;
  value: string;
  hex?: string | null;
};

const ShareOutlineIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.75}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...props}
  >
    <path d="M12 4v7" />
    <path d="M9 8l3-3 3 3" />
    <path d="M6 10v7a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-7" />
  </svg>
);

export default function ProductDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const addItem = useCartStore((state) => state.addItem);
  const cartError = useCartStore((state) => state.error);
  const { currentCurrency: preferredCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();

  const [product, setProduct] = useState<Product | null>(null);
  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string | null>(null);
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [isInWishlist, setIsInWishlist] = useState(false);
  const [wishlistLoading, setWishlistLoading] = useState(false);
  const [sizeGuideOpen, setSizeGuideOpen] = useState(false);
  const [sizeMenuOpen, setSizeMenuOpen] = useState(false);
  const [bagModalOpen, setBagModalOpen] = useState(false);
  const [addToBagError, setAddToBagError] = useState<string | null>(null);
  const [addedVariant, setAddedVariant] = useState<ProductVariant | null>(null);
  const sizeDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) {
      navigate('/');
      return;
    }

    // Fetch exchange rates on mount
    fetchExchangeRate();

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

        // Check if product is in wishlist (only if user is logged in)
        const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
        if (token) {
          checkWishlistStatus(data.id);
        }
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

  // Effect to switch images when color variation is selected
  useEffect(() => {
    const normalizedColor = normalizeValue(selectedColor);

    if (!product || !normalizedColor) {
      // If no color selected, use default product images
      if (product?.images?.[0]?.image_url) {
        setSelectedImage(product.images[0].image_url);
      }
      return;
    }

    // Find the variation matching the selected color
    // Note: Variation titles are formatted as "Product Name (Color)", so we check if title contains the color
    const selectedVariation = product.variations?.find((variation) =>
      normalizeValue(variation.title).includes(normalizedColor)
    );

    if (selectedVariation && selectedVariation.images.length > 0) {
      // Switch to variation's first image
      setSelectedImage(selectedVariation.images[0]);
    } else {
      // Fallback to product's default images if variation has no images
      if (product.images?.[0]?.image_url) {
        setSelectedImage(product.images[0].image_url);
      }
    }
  }, [selectedColor, product]);

  const checkWishlistStatus = async (productId: string) => {
    try {
      const result = await wishlistService.checkInWishlist(productId);
      setIsInWishlist(result.in_wishlist);
    } catch (err) {
      // If error (e.g., not authenticated), just keep wishlist as false
      console.error('Error checking wishlist status:', err);
    }
  };

  const loadRelatedProducts = async (vendorId: string, currentProductId: string) => {
    try {
      const response = await productService.getProducts({
        vendor_id: vendorId,
        page_size: 12,
      });
      const filtered = response.products.filter((item) => item.id !== currentProductId);
      setRelatedProducts(filtered.slice(0, 8));
    } catch (err) {
      console.error('Failed to load related products', err);
    }
  };

  const normalizeValue = (value?: string | null) => value?.trim().toLowerCase() ?? '';

  const getColorOptions = (variants: ProductVariant[]): ColorOption[] => {
    const uniqueMap = new Map<string, ColorOption>();
    variants.forEach((variant) => {
      if (variant.color) {
        const key = normalizeValue(variant.color);
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
    const normalizeSelection = {
      color: normalizeValue(selectedColor),
      size: normalizeValue(selectedSize),
    };

    if (!product?.variants?.length) {
      // For products without variants, create a default variant
      if (!product) return null;

      return {
        id: `default-${product.id}`,
        product_id: product.id,
        price: product.base_price,
        compare_at_price: product.compare_at_price,
        stock: product.total_stock,
        is_available: product.total_stock > 0,
      } as ProductVariant;
    }

    const variants = product.variants;

    const hasColorSelection = Boolean(normalizeSelection.color);
    const hasSizeSelection = Boolean(normalizeSelection.size);

    const strictMatch = variants.find((variant) => {
      const variantColor = normalizeValue(variant.color);
      const variantSize = normalizeValue(variant.size);

      const colorMatches = !hasColorSelection || variantColor === normalizeSelection.color;
      const sizeMatches = !hasSizeSelection || variantSize === normalizeSelection.size;

      return colorMatches && sizeMatches;
    });

    if (strictMatch) {
      return strictMatch;
    }

    if (hasColorSelection && hasSizeSelection) {
      return null;
    }

    if (hasColorSelection) {
      return (
        variants.find(
          (variant) => normalizeValue(variant.color) === normalizeSelection.color
        ) ?? null
      );
    }

    if (hasSizeSelection) {
      return (
        variants.find(
          (variant) => normalizeValue(variant.size) === normalizeSelection.size
        ) ?? null
      );
    }

    return variants[0] ?? null;
  }, [product, colorOptions.length, sizeOptions.length, selectedColor, selectedSize]);

  const hasInvalidSelection = useMemo(() => {
    if (!product?.variants?.length) return false;
    if (!selectedColor && !selectedSize) return false;

    return !selectedVariant;
  }, [product?.variants?.length, selectedColor, selectedSize, selectedVariant]);

  const currentPrice = selectedVariant?.price ?? product?.base_price ?? 0;
  const comparePrice = selectedVariant?.compare_at_price ?? product?.compare_at_price ?? null;

  const baseStock = product?.total_stock ?? 0;
  const variantStock = selectedVariant?.stock ?? null;
  const maxQuantity = variantStock !== null ? variantStock : baseStock;
  const isOutOfStock = maxQuantity <= 0;

  useEffect(() => {
    if (!selectedVariant) {
      setQuantity(1);
      return;
    }
    const stock = selectedVariant.stock ?? 0;
    if (stock <= 0) {
      setQuantity(0);
    } else {
      setQuantity((prev) => {
        if (prev <= 0) return 1;
        return Math.min(prev, stock);
      });
    }
  }, [selectedVariant?.id, selectedVariant?.stock]);

  useEffect(() => {
    if (cartError) {
      console.error('[ProductDetail] Cart synchronization error', {
        productId: product?.id,
        variantId: selectedVariant?.id,
        cartError,
      });
      setAddToBagError(cartError);
    }
  }, [cartError, product?.id, selectedVariant?.id]);

  const handleQuantityChange = (direction: 'increment' | 'decrement') => {
    if (isOutOfStock) return;
    if (direction === 'increment') {
      setQuantity((prev) => Math.min(prev + 1, maxQuantity));
    } else {
      setQuantity((prev) => Math.max(prev - 1, 1));
    }
  };

  const handleAddToBag = () => {
    setAddToBagError(null);

    if (missingSelection) {
      console.warn('[ProductDetail] Add to bag blocked: missing selection', {
        productId: product?.id,
        selectedColor,
        selectedSize,
      });
      setAddToBagError('Select a color and size to add this item to your bag.');
      return;
    }

    if (hasInvalidSelection) {
      console.warn('[ProductDetail] Add to bag blocked: invalid selection', {
        productId: product?.id,
        selectedColor,
        selectedSize,
      });
      setAddToBagError('This color and size combination is unavailable. Please choose another option.');
      return;
    }

    if (!product || !selectedVariant) {
      console.error('[ProductDetail] Add to bag failed: missing product or variant', {
        productId: product?.id,
        variantId: selectedVariant?.id,
        availableVariants: product?.variants?.length,
        availableVariations: product?.variations?.length,
      });
      setAddToBagError('We could not find the selected variation. Please refresh and try again.');
      return;
    }

    if (isOutOfStock || quantity < 1) {
      console.warn('[ProductDetail] Add to bag blocked: item out of stock or invalid quantity', {
        productId: product.id,
        variantId: selectedVariant.id,
        quantity,
        maxQuantity,
      });
      setAddToBagError('This variation is currently unavailable.');
      return;
    }

    if (quantity > maxQuantity) {
      console.warn('[ProductDetail] Quantity adjusted to available stock', {
        productId: product.id,
        variantId: selectedVariant.id,
        requested: quantity,
        maxQuantity,
      });
      setQuantity(maxQuantity);
      setAddToBagError('Quantity adjusted to available stock.');
      return;
    }

    try {
      // Add to cart using Zustand store
      addItem({
        product,
        variant: selectedVariant,
        quantity,
      });

      setAddedVariant(selectedVariant);
      setBagModalOpen(true);
    } catch (err) {
      console.error('[ProductDetail] Unexpected error while adding to bag', {
        productId: product.id,
        variantId: selectedVariant.id,
        err,
      });
      setAddToBagError('Unable to add to bag. Check console logs for details.');
    }
  };

  const handleWishlistToggle = async () => {
    if (!product) return;

    // Check if user is logged in
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    console.log('Token exists:', !!token);

    if (!token) {
      // Redirect to login page
      console.log('No token, redirecting to login');
      navigate('/auth/login');
      return;
    }

    console.log('Toggling wishlist for product:', product.id, 'Current state:', isInWishlist);
    setWishlistLoading(true);
    try {
      if (isInWishlist) {
        // Remove from wishlist
        console.log('Removing from wishlist');
        await wishlistService.removeFromWishlist(product.id);
        setIsInWishlist(false);
        console.log('Removed successfully');
      } else {
        // Add to wishlist
        console.log('Adding to wishlist');
        const result = await wishlistService.addToWishlist(product.id);
        console.log('Added successfully:', result);
        setIsInWishlist(true);
      }
    } catch (err: any) {
      console.error('Error toggling wishlist:', err);
      console.error('Error response:', err?.response?.data);
      console.error('Error status:', err?.response?.status);
      // TODO: Show error toast notification
      alert(`Failed to update wishlist: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setWishlistLoading(false);
    }
  };

  const handleShare = async () => {
    if (!product) return;

    const shareUrl = window.location.href;
    const shareData = {
      title: product.title,
      text: product.description ?? product.title,
      url: shareUrl,
    };

    try {
      if (navigator.share) {
        await navigator.share(shareData);
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(shareUrl);
        alert('Product link copied to clipboard');
      } else {
        alert('Sharing is not supported in this browser.');
      }
    } catch (err) {
      console.error('Error sharing product:', err);
    }
  };

  const missingSelection =
    (colorOptions.length > 0 && !selectedColor) ||
    (sizeOptions.length > 0 && !selectedSize);

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;

  // Get ALL images: product images + all variation images
  const getDisplayImages = () => {
    if (!product) return [];

    const allImages = [];

    // Add product default images first
    if (product.images && product.images.length > 0) {
      allImages.push(...product.images);
    }

    // Add images from ALL variations
    if (product.variations && product.variations.length > 0) {
      product.variations.forEach((variation) => {
        if (variation.images && variation.images.length > 0) {
          // Map variation image URLs to ProductImage format for consistency
          const variationImages = variation.images.map((url, index) => ({
            id: `variation-${variation.id}-${index}`,
            product_id: product.id,
            image_url: url,
            display_order: allImages.length + index,
            is_primary: false,
          }));
          allImages.push(...variationImages);
        }
      });
    }

    return allImages;
  };

  const galleryImages = getDisplayImages();

  // Show gallery if product has multiple images (regardless of variations)
  const shouldShowGallery = galleryImages.length > 1;

  const sizeGuideData = product?.size_guide && (product.size_guide.rows?.length ?? 0) > 0 ? product.size_guide : FALLBACK_SIZE_GUIDE;
  const sizeGuideRows = sizeGuideData.rows ?? [];
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

  // Calculate savings percentage
  const savingsPercent = comparePrice && comparePrice > currentPrice
    ? Math.round(((comparePrice - currentPrice) / comparePrice) * 100)
    : 0;

  return (
    <Layout>
    <section className="bg-[var(--color-page-bg)]">
      <div className="grid grid-cols-1 lg:grid-cols-[auto_minmax(0,520px)] lg:gap-16 mb-16">
        {/* LEFT COLUMN - IMAGES (Full bleed to left edge) */}
        <div className="relative -mt-32 pt-32">
          {/* Main Image - extends up into header area and flush to left */}
          <div className="relative overflow-hidden bg-[#f5f7f8] aspect-[3/4] w-full lg:w-[calc(50vw+200px)] lg:max-w-[800px]">
              <img
                src={heroImage}
                alt={product.title}
                className="w-full h-full object-cover"
                onError={(event) => {
                  event.currentTarget.src = placeholderImage;
                  event.currentTarget.onerror = null;
                }}
              />

              {/* Thumbnail Gallery - overlaid at bottom of main image */}
              {shouldShowGallery && (
                <div className="absolute bottom-6 left-6 right-6 overflow-x-auto overflow-y-hidden scrollbar-hide">
                  <div className="flex gap-2 min-w-max pr-6">
                    {galleryImages.map((image) => (
                      <button
                        key={image.id}
                        type="button"
                        onClick={() => setSelectedImage(image.image_url)}
                        className={`overflow-hidden border-2 transition-all duration-200 w-16 h-20 flex-shrink-0 ${
                          selectedImage === image.image_url
                            ? 'border-white shadow-lg ring-1 ring-white/30'
                            : 'border-white/50 hover:border-white shadow-md'
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
                </div>
              )}
            </div>
          </div>

          {/* RIGHT COLUMN - PRODUCT SUMMARY */}
          <div className="space-y-8 lg:pt-12 px-4 sm:px-6 lg:px-0 lg:pr-12 lg:max-w-[520px] lg:ml-auto">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2 flex-1 min-w-0">
                {/* Brand/Vendor Name */}
                {product.vendor_name && (
                  <p className="text-xs font-ui uppercase tracking-[0.25em] text-primary">
                    {product.vendor_name}
                  </p>
                )}

                {/* Product Title */}
                <h1 className="text-4xl lg:text-5xl font-display text-primary leading-tight -mt-2">
                  {product.title}
                </h1>
              </div>

              <div className="flex items-center gap-2 text-primary">
                <button
                  type="button"
                  onClick={handleWishlistToggle}
                  disabled={wishlistLoading}
                  className={`h-12 w-12 flex items-center justify-center text-primary transition ${
                    wishlistLoading ? 'opacity-50 cursor-not-allowed' : 'hover:text-primary-dark'
                  }`}
                  aria-label={isInWishlist ? 'Remove from wishlist' : 'Add to wishlist'}
                >
                  <Bookmark
                    className="w-5 h-5"
                    strokeWidth={1.75}
                    fill={isInWishlist ? 'currentColor' : 'none'}
                  />
                </button>
                <button
                  type="button"
                  onClick={handleShare}
                  className="h-12 w-12 flex items-center justify-center text-primary hover:text-primary-dark transition"
                  aria-label="Share product"
                >
                  <ShareOutlineIcon className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Pricing Block */}
            <div className="space-y-3 text-primary">
              <div className="flex items-baseline gap-3">
                {comparePrice && comparePrice > currentPrice && (
                  <span className="text-xl font-ui text-primary/60 line-through">
                    {formatPriceWithConversion(Number(comparePrice), product.currency, preferredCurrency, exchangeRates)}
                  </span>
                )}
                <span className="text-2xl font-ui font-semibold text-primary">
                  {formatPriceWithConversion(Number(currentPrice), product.currency, preferredCurrency, exchangeRates)}
                </span>
              </div>
              {savingsPercent > 0 && (
                <div className="inline-block bg-primary px-3 py-1">
                  <span className="text-xs font-ui uppercase tracking-[0.15em] text-white font-semibold">
                    {savingsPercent}% OFF
                  </span>
                </div>
              )}
            </div>

            {/* Short Description */}
            {product.description && (
              <p className="text-base font-serif text-primary leading-relaxed">
                {product.description}
              </p>
            )}

            {/* Made to Order / Info Line */}
            {product.made_to_order && (
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" strokeWidth="2"/>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 16v-4m0-4h.01"/>
                </svg>
                <span className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                  Made to Order{product.made_to_order_timeline && ` • ${product.made_to_order_timeline}`}
                </span>
              </div>
            )}

            {/* Size Selector and Quantity Row */}
            {sizeOptions.length > 0 && (
              <div className="space-y-4 border-t border-primary/20 pt-8">
                {/* Select Size Dropdown + Quantity Controls on same row */}
                <div className="flex items-center justify-between gap-8">
                  {/* Size Dropdown */}
                  <div className="flex-1 relative" ref={sizeDropdownRef}>
                    <button
                      type="button"
                      className="w-full text-left text-base font-ui text-primary flex items-center justify-between pb-2 border-b border-primary/30 hover:border-primary transition"
                      onClick={() => setSizeMenuOpen((prev) => !prev)}
                    >
                      <span>{selectedSize || 'Select Size'}</span>
                      <svg
                        className={`w-4 h-4 text-primary/70 transition-transform ${sizeMenuOpen ? 'rotate-180' : ''}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {sizeMenuOpen && (
                      <div className="absolute z-20 mt-1 w-full bg-white border border-primary/20 shadow-lg max-h-48 overflow-y-auto">
                        {sizeOptions.map((size) => (
                          <button
                            key={size}
                            type="button"
                            onClick={() => {
                              setSelectedSize(size);
                              setSizeMenuOpen(false);
                            }}
                            className={`w-full text-left px-4 py-2.5 text-sm font-ui transition ${
                              selectedSize === size
                                ? 'bg-primary/5 text-primary font-semibold'
                                : 'text-primary hover:bg-primary/5'
                            }`}
                          >
                            {size}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Quantity Controls - clean, no border */}
                  <div className="flex items-center gap-4">
                    <button
                      type="button"
                      className="text-primary/70 hover:text-primary transition disabled:opacity-30"
                      onClick={() => handleQuantityChange('decrement')}
                      disabled={isOutOfStock || quantity <= 1}
                    >
                      <Minus className="w-5 h-5" />
                    </button>
                    <span className="text-lg font-ui text-primary min-w-[24px] text-center">{quantity}</span>
                    <button
                      type="button"
                      className="text-primary/70 hover:text-primary transition disabled:opacity-30"
                      onClick={() => handleQuantityChange('increment')}
                      disabled={isOutOfStock || quantity >= maxQuantity}
                    >
                      <Plus className="w-5 h-5" />
                    </button>
                  </div>
                </div>

                {/* Find Your Size label */}
                <p className="text-xs font-ui uppercase tracking-[0.2em] text-primary/70">
                  Find your size
                </p>
              </div>
            )}

            {/* Color Selector */}
            {colorOptions.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-base font-ui text-primary">Colors:</p>
                  {selectedColor && (
                    <p className="text-sm font-ui uppercase tracking-[0.2em] text-primary font-semibold">
                      {selectedColor}
                    </p>
                  )}
                </div>
                <div className="flex gap-3 flex-wrap">
                  {colorOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setSelectedColor(option.value)}
                      className={`w-11 h-11 border-2 transition-all ${
                        selectedColor === option.value
                          ? 'border-primary ring-2 ring-primary/25'
                          : 'border-primary/30 hover:border-primary/60'
                      }`}
                      style={{
                        backgroundColor: option.hex ?? '#f5f5f5',
                      }}
                      aria-label={`Select color ${option.label}`}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Inventory Note */}
            {!isOutOfStock && maxQuantity > 0 && maxQuantity <= 10 && (
              <p className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                Only {maxQuantity} left in stock
              </p>
            )}

            {/* Add to Bag Button */}
            <button
              type="button"
              disabled={missingSelection || isOutOfStock || quantity < 1}
              className={`w-full py-4 text-sm font-ui uppercase tracking-[0.2em] transition-colors ${
                missingSelection || isOutOfStock || quantity < 1
                  ? 'bg-gray-300 text-primary/60 cursor-not-allowed'
                  : 'bg-primary text-white hover:bg-primary-dark'
              }`}
              onClick={handleAddToBag}
            >
              Add to Bag
            </button>
            {addToBagError && (
              <p className="mt-3 text-sm text-red-600" role="alert">
                {addToBagError}
              </p>
            )}
          </div>
        </div>

      {/* Content sections with max-width container */}
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 text-primary">
        {/* PRODUCT INFORMATION SECTION */}
        <div className="mt-16 mb-16 pb-12 border-b border-primary/20">
          <h2 className="text-2xl font-display text-primary mb-8">Product information</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {/* Sustainability */}
            <div className="space-y-2">
              <h3 className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                Sustainability
              </h3>
              <p className="text-sm font-serif text-primary/80 leading-relaxed">
                Crafted from sustainably sourced materials. Our artisans follow eco-friendly practices, ensuring minimal environmental impact while creating timeless pieces.
              </p>
            </div>

            {/* Product Care */}
            {product?.care_instructions && (
              <div className="space-y-2">
                <h3 className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                  Product Care
                </h3>
                <p className="text-sm font-serif text-primary/80 leading-relaxed">
                  {product.care_instructions}
                </p>
              </div>
            )}

            {/* Fabric Composition */}
            {product?.fabric_composition && (
              <div className="space-y-2">
                <h3 className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                  Fabric & Materials
                </h3>
                <p className="text-sm font-serif text-primary/80 leading-relaxed">
                  {product.fabric_composition}
                </p>
              </div>
            )}

            {/* Delivery and Shipping */}
            <div className="space-y-2">
              <h3 className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                Delivery and Shipping
              </h3>
              <p className="text-sm font-serif text-primary/80 leading-relaxed">
                Free delivery on orders over {formatPriceWithCurrency(30000, preferredCurrency)}. Standard delivery within 5-7 business days. Express options available at checkout.
              </p>
            </div>

            {/* Gifting */}
            <div className="space-y-2">
              <h3 className="text-xs font-ui uppercase tracking-[0.2em] text-primary">
                Gifting
              </h3>
              <p className="text-sm font-serif text-primary/80 leading-relaxed">
                Complimentary gift wrapping available. Add a personalized note at checkout to make your gift extra special.
              </p>
            </div>
          </div>
        </div>

        {/* SHOP THE LOOK SECTION */}
        {relatedProducts.length > 0 && (
          <div className="mb-16">
            <h2 className="text-2xl font-display text-primary mb-6">Shop The Look</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 lg:gap-6">
              {relatedProducts.slice(0, 4).map((related) => (
                <ProductCard product={related} key={related.id} />
              ))}
            </div>
          </div>
        )}

        {/* YOU MAY ALSO LIKE SECTION */}
        {relatedProducts.length > 4 && (
          <div className="mb-8">
            <h2 className="text-2xl font-display text-primary mb-6">You May Also Like</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 lg:gap-6">
              {relatedProducts.slice(4, 8).map((related) => (
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
              className="absolute top-6 right-6 text-primary/70 hover:text-primary"
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
                <p className="text-xs uppercase tracking-[0.3em] text-primary/70">
                {sizeGuideData?.gender || 'Size Guide'}
                </p>
                <h3 className="text-2xl font-display font-bold text-primary">
                {sizeGuideData?.title || product.title}
                </h3>
                <p className="text-sm text-primary/80">
                {sizeGuideData?.subtitle || product.category_name || product.collection_name || 'Collection'}
                </p>
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm font-semibold text-primary border-b border-primary/20 pb-2">
                <span>Conversion Chart</span>
                <span>Inches / CM</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="uppercase text-xs tracking-[0.3em] text-primary/70">
                      <th className="py-3">Size</th>
                      <th className="py-3">Standard</th>
                      <th className="py-3">Measurement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sizeGuideRows.length
                      ? sizeGuideRows.map((row) => (
                          <tr key={row.label} className="border-t border-primary/15 text-primary">
                            <td className="py-3 font-semibold">{row.label}</td>
                            <td className="py-3 uppercase">{row.standard ?? '—'}</td>
                            <td className="py-3">{row.measurement ?? '—'}</td>
                          </tr>
                        ))
                      : (
                        <tr className="border-t border-primary/15 text-primary/70">
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
