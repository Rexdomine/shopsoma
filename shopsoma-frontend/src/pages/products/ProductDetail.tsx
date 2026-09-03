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
import { formatPriceWithConversion } from '../../utils/pricing';
import { useCurrencyStore } from '../../store/currencyStore';
import { hasSolidColorHex, normalizeColorValue } from '../../utils/colorDisplay';
import { getProductImageSources, normalizeProductImageUrl } from '../../utils/productImages';

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
  isSolid: boolean;
};

type GalleryImage = {
  id: string;
  src: string;
  fallbackSrc?: string;
  altText?: string;
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
        setSelectedImage(getProductImageSources(data)[0]?.src ?? null);

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
    const normalizedColor = normalizeColorValue(selectedColor);

    if (!product || !normalizedColor) {
      // If no color selected, use default product images
      const defaultImage = product ? getProductImageSources(product)[0]?.src : null;
      if (defaultImage) {
        setSelectedImage(defaultImage);
      }
      return;
    }

    // Find the variation matching the selected color
    // Note: Variation titles are formatted as "Product Name (Color)", so we check if title contains the color
    const selectedVariation = product.variations?.find((variation) => {
      const normalizedTitle = normalizeColorValue(variation.title);
      return normalizedTitle === normalizedColor || normalizedTitle.includes(normalizedColor);
    });

    if (selectedVariation && selectedVariation.images.length > 0) {
      // Switch to variation's first image
      const variationImage = normalizeProductImageUrl(selectedVariation.images[0]);
      if (variationImage) {
        setSelectedImage(variationImage);
      }
    } else {
      // Fallback to product's default images if variation has no images
      const defaultImage = getProductImageSources(product)[0]?.src;
      if (defaultImage) {
        setSelectedImage(defaultImage);
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

  const getColorOptions = (
    variants: ProductVariant[],
    sizeFilter?: string | null
  ): ColorOption[] => {
    const uniqueMap = new Map<string, ColorOption>();
    const normalizedSize = normalizeColorValue(sizeFilter);

    variants.forEach((variant) => {
      if (!variant.color) return;
      if (normalizedSize && normalizeColorValue(variant.size) !== normalizedSize) return;

      const key = normalizeColorValue(variant.color);
      if (!uniqueMap.has(key)) {
        uniqueMap.set(key, {
          label: variant.color,
          value: variant.color,
          hex: variant.color_hex ?? null,
          isSolid: hasSolidColorHex(variant.color_hex),
        });
      }
    });
    return Array.from(uniqueMap.values());
  };

  const getSizeOptions = (
    variants: ProductVariant[],
    colorFilter?: string | null
  ): string[] => {
    const set = new Set<string>();
    const normalizedColor = normalizeColorValue(colorFilter);

    variants.forEach((variant) => {
      if (!variant.size) return;
      if (normalizedColor && normalizeColorValue(variant.color) !== normalizedColor) return;

      set.add(variant.size);
    });
    return Array.from(set);
  };

  const colorOptions = useMemo(
    () => getColorOptions(product?.variants ?? [], selectedSize),
    [product?.variants, selectedSize]
  );
  const sizeOptions = useMemo(
    () => getSizeOptions(product?.variants ?? [], selectedColor),
    [product?.variants, selectedColor]
  );

  useEffect(() => {
    if (!selectedColor || colorOptions.length === 0) return;
    const normalizedSelected = normalizeColorValue(selectedColor);
    const isValid = colorOptions.some(
      (option) => normalizeColorValue(option.value) === normalizedSelected
    );
    if (!isValid) {
      setSelectedColor(null);
    }
  }, [selectedColor, colorOptions]);

  useEffect(() => {
    if (!selectedSize || sizeOptions.length === 0) return;
    const normalizedSelected = normalizeColorValue(selectedSize);
    const isValid = sizeOptions.some(
      (option) => normalizeColorValue(option) === normalizedSelected
    );
    if (!isValid) {
      setSelectedSize(null);
    }
  }, [selectedSize, sizeOptions]);

  const selectedVariant = useMemo(() => {
    const normalizeSelection = {
      color: normalizeColorValue(selectedColor),
      size: normalizeColorValue(selectedSize),
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
        is_available: product.made_to_order ? true : product.total_stock > 0,
      } as ProductVariant;
    }

    const variants = product.variants;

    const hasColorSelection = Boolean(normalizeSelection.color);
    const hasSizeSelection = Boolean(normalizeSelection.size);

    const strictMatch = variants.find((variant) => {
      const variantColor = normalizeColorValue(variant.color);
      const variantSize = normalizeColorValue(variant.size);

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
          (variant) => normalizeColorValue(variant.color) === normalizeSelection.color
        ) ?? null
      );
    }

    if (hasSizeSelection) {
      return (
        variants.find(
          (variant) => normalizeColorValue(variant.size) === normalizeSelection.size
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
  const usesInventoryTracking = !product?.made_to_order;
  const maxQuantity = usesInventoryTracking
    ? (variantStock !== null ? variantStock : baseStock)
    : 99;
  const isOutOfStock = usesInventoryTracking ? maxQuantity <= 0 : false;

  useEffect(() => {
    if (!selectedVariant) {
      setQuantity(1);
      return;
    }
    if (!usesInventoryTracking) {
      setQuantity((prev) => (prev <= 0 ? 1 : Math.min(prev, 99)));
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
  }, [selectedVariant?.id, selectedVariant?.stock, usesInventoryTracking]);

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

    if (usesInventoryTracking && quantity > maxQuantity) {
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

  const handleProductImageError = (
    event: React.SyntheticEvent<HTMLImageElement>,
    fallbackSrc?: string
  ) => {
    const image = event.currentTarget;
    if (fallbackSrc && image.dataset.fallbackApplied !== 'true') {
      image.dataset.fallbackApplied = 'true';
      image.src = fallbackSrc;
      return;
    }
    image.src = placeholderImage;
    image.onerror = null;
  };

  // Get ALL images: product images + all variation images
  const getDisplayImages = (): GalleryImage[] => {
    if (!product) return [];

    return getProductImageSources(product).map((image, index) => ({
      id: `${product.id}-gallery-${index}-${image.src}`,
      src: image.src,
      fallbackSrc: image.fallbackSrc,
      altText: product.title,
    }));
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

  const heroImage = selectedImage ?? galleryImages[0]?.src ?? placeholderImage;
  const heroFallbackImage = galleryImages.find((image) => image.src === heroImage)?.fallbackSrc;

  // Calculate savings percentage
  const savingsPercent = comparePrice && comparePrice > currentPrice
    ? Math.round(((comparePrice - currentPrice) / comparePrice) * 100)
    : 0;
  const productInfoItems = [
    product.description
      ? {
          title: 'Product Notes',
          body: product.description,
        }
      : null,
    product.fabric_composition
      ? {
          title: 'Fabric & Materials',
          body: product.fabric_composition,
        }
      : null,
    product.care_instructions
      ? {
          title: 'Product Care',
          body: product.care_instructions,
        }
      : null,
    product.made_to_order
      ? {
          title: 'Made To Order',
          body: product.made_to_order_timeline
            ? `Made to order. Estimated production timeline: ${product.made_to_order_timeline}.`
            : 'Made to order.',
        }
      : null,
    product.category_name || product.collection_name
      ? {
          title: 'Category',
          body: [product.category_parent_name, product.category_name, product.collection_name]
            .filter(Boolean)
            .join(' / '),
        }
      : null,
  ].filter((item): item is { title: string; body: string } => Boolean(item && item.body));

  return (
    <Layout>
    <section className="w-full overflow-x-clip bg-[var(--color-page-bg)] text-primary">
      <main className="mx-auto flex max-w-7xl flex-col gap-10 px-6 py-10 md:flex-row md:gap-12 lg:py-12">
        <div className="md:w-1/2">
          <div className="relative aspect-[4/5] w-full overflow-hidden bg-[#f5f7f8]">
            <div className="flex h-full w-full items-center justify-center lg:justify-end">
              <div className="h-full w-full">
                <img
                  src={heroImage}
                  alt={product.title}
                  className="h-full w-full object-contain object-center"
                  onError={(event) => handleProductImageError(event, heroFallbackImage)}
                />
              </div>
            </div>
          </div>

          {shouldShowGallery && (
            <div className="mt-4 w-full overflow-x-auto overflow-y-hidden pb-1 scrollbar-hide">
              <div className="flex min-w-max gap-3">
                {galleryImages.map((image) => (
                  <button
                    key={image.id}
                    type="button"
                    onClick={() => setSelectedImage(image.src)}
                    className={`h-20 w-16 flex-shrink-0 overflow-hidden border-2 bg-[#f5f7f8] p-0.5 transition-all duration-200 ${
                      (selectedImage ?? galleryImages[0]?.src) === image.src
                        ? 'border-primary shadow-md'
                        : 'border-primary/20 hover:border-primary/50'
                    }`}
                    aria-label={`View ${product.title} image`}
                  >
                    <img
                      src={image.src}
                      alt={image.altText ?? product.title}
                      className="h-full w-full object-cover object-center"
                      onError={(event) => handleProductImageError(event, image.fallbackSrc)}
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="mx-auto flex w-full max-w-md flex-col justify-center md:w-1/2">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              {product.vendor_name && (
                <p className="font-ui text-sm uppercase tracking-[0.25em] text-primary/60">
                  {product.vendor_name}
                </p>
              )}
              <h1 className="mt-2 text-3xl font-display font-medium leading-tight text-primary md:text-4xl">
                {product.title}
              </h1>
            </div>

            <div className="flex shrink-0 items-center gap-3 text-primary/60">
              <button
                type="button"
                onClick={handleWishlistToggle}
                disabled={wishlistLoading}
                className={`transition hover:text-primary ${
                  wishlistLoading ? 'cursor-not-allowed opacity-50' : ''
                }`}
                aria-label={isInWishlist ? 'Remove from wishlist' : 'Add to wishlist'}
              >
                <Bookmark
                  className="h-5 w-5"
                  strokeWidth={1.5}
                  fill={isInWishlist ? 'currentColor' : 'none'}
                />
              </button>
              <button
                type="button"
                onClick={handleShare}
                className="transition hover:text-primary"
                aria-label="Share product"
              >
                <ShareOutlineIcon className="h-5 w-5" />
              </button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 font-ui">
            {comparePrice && comparePrice > currentPrice && (
              <span className="text-base text-primary/40 line-through">
                {formatPriceWithConversion(Number(comparePrice), product.currency, preferredCurrency, exchangeRates)}
              </span>
            )}
            <span className="text-lg text-primary">
              {formatPriceWithConversion(Number(currentPrice), product.currency, preferredCurrency, exchangeRates)}
            </span>
            {savingsPercent > 0 && (
              <span className="bg-primary px-2.5 py-1 text-xs uppercase tracking-[0.18em] text-white">
                {savingsPercent}% Off
              </span>
            )}
          </div>

          <div className="mt-8 space-y-6">
            {sizeOptions.length > 0 && (
              <div className="space-y-3">
                <div className="relative border-b border-primary/25 pb-2" ref={sizeDropdownRef}>
                  <button
                    type="button"
                    className="flex w-full cursor-pointer items-center justify-between bg-transparent pb-2 text-left font-ui text-sm text-primary/75 transition hover:text-primary"
                    onClick={() => setSizeMenuOpen((prev) => !prev)}
                  >
                    <span>{selectedSize || 'Select Size'}</span>
                    <svg
                      className={`h-4 w-4 text-primary/50 transition-transform ${sizeMenuOpen ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {sizeMenuOpen && (
                    <div className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto border border-primary/15 bg-white shadow-lg">
                      {sizeOptions.map((size) => (
                        <button
                          key={size}
                          type="button"
                          onClick={() => {
                            setSelectedSize(size);
                            setSizeMenuOpen(false);
                          }}
                          className={`w-full px-4 py-2.5 text-left font-ui text-sm transition ${
                            selectedSize === size
                              ? 'bg-primary/5 font-semibold text-primary'
                              : 'text-primary/75 hover:bg-primary/5 hover:text-primary'
                          }`}
                        >
                          {size}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {hasSizeGuide && (
                  <button
                    type="button"
                    onClick={() => setSizeGuideOpen(true)}
                    className="block font-ui text-xs uppercase tracking-[0.2em] text-primary/60 underline underline-offset-4 transition hover:text-primary"
                  >
                    Find your size
                  </button>
                )}
              </div>
            )}

            {colorOptions.length > 0 && (
              <div>
                <div className="mb-3 flex items-center justify-between gap-4">
                  <span className="font-ui text-sm uppercase tracking-[0.18em] text-primary/60">
                    Colors:
                  </span>
                  {selectedColor && (
                    <span className="font-ui text-xs font-bold uppercase tracking-[0.2em] text-primary">
                      {selectedColor}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {colorOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setSelectedColor(option.value)}
                      className={`transition ${
                        option.isSolid
                          ? `h-12 w-12 border-2 p-0.5 ${
                              selectedColor === option.value
                                ? 'border-primary'
                                : 'border-primary/20 hover:border-primary/50'
                            }`
                          : `border px-4 py-2 font-ui text-xs uppercase tracking-[0.12em] ${
                              selectedColor === option.value
                                ? 'border-primary bg-primary text-white'
                                : 'border-primary/20 text-primary hover:border-primary/50'
                            }`
                      }`}
                      aria-label={`Select color ${option.label}`}
                    >
                      {option.isSolid ? (
                        <span
                          className="block h-full w-full"
                          style={{ backgroundColor: option.hex ?? '#f5f5f5' }}
                        />
                      ) : (
                        option.label
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between gap-6 border-y border-primary/15 py-4">
              <span className="font-ui text-xs uppercase tracking-[0.2em] text-primary/60">
                Quantity
              </span>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  className="text-primary/60 transition hover:text-primary disabled:opacity-30"
                  onClick={() => handleQuantityChange('decrement')}
                  disabled={isOutOfStock || quantity <= 1}
                  aria-label="Decrease quantity"
                >
                  <Minus className="h-5 w-5" />
                </button>
                <span className="min-w-[24px] text-center font-ui text-base text-primary">{quantity}</span>
                <button
                  type="button"
                  className="text-primary/60 transition hover:text-primary disabled:opacity-30"
                  onClick={() => handleQuantityChange('increment')}
                  disabled={isOutOfStock || quantity >= maxQuantity}
                  aria-label="Increase quantity"
                >
                  <Plus className="h-5 w-5" />
                </button>
              </div>
            </div>

            {product.made_to_order && (
              <p className="font-ui text-xs uppercase tracking-[0.2em] text-primary/70">
                Made to Order{product.made_to_order_timeline && ` / ${product.made_to_order_timeline}`}
              </p>
            )}

            {usesInventoryTracking && !isOutOfStock && maxQuantity > 0 && maxQuantity <= 10 && (
              <p className="font-ui text-xs uppercase tracking-[0.2em] text-red-500">
                Only {maxQuantity} left in stock
              </p>
            )}

            <button
              type="button"
              disabled={missingSelection || isOutOfStock || quantity < 1}
              className={`w-full py-4 font-ui text-sm uppercase tracking-[0.2em] transition-colors ${
                missingSelection || isOutOfStock || quantity < 1
                  ? 'cursor-not-allowed bg-primary/15 text-primary/45'
                  : 'bg-primary text-white hover:bg-primary-dark'
              }`}
              onClick={handleAddToBag}
            >
              {isOutOfStock ? 'Out of Stock' : 'Add to Bag'}
            </button>
            {addToBagError && (
              <p className="text-sm text-red-600" role="alert">
                {addToBagError}
              </p>
            )}

            {product.description && (
              <p className="font-ui text-sm leading-relaxed text-primary/70">
                {product.description}
              </p>
            )}
          </div>
        </div>
      </main>

      {productInfoItems.length > 0 && (
        <section className="border-t border-primary/20">
          <div className="mx-auto max-w-7xl px-6 py-12">
            <h2 className="mb-8 text-2xl font-display text-primary">Product information</h2>
            <div className="grid grid-cols-1 gap-x-16 gap-y-10 md:grid-cols-2">
              {productInfoItems.map((item) => (
                <div key={item.title} className="flex flex-col md:flex-row md:gap-8">
                  <h3 className="mb-2 w-40 shrink-0 font-ui text-xs font-bold uppercase tracking-[0.2em] text-primary/70 md:mb-0">
                    {item.title}
                  </h3>
                  <p className="font-ui text-sm leading-relaxed text-primary/60">
                    {item.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {relatedProducts.length > 0 && (
        <section className="mx-auto max-w-7xl px-6 py-12">
          <h2 className="mb-8 text-2xl font-display text-primary">Shop The Look</h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {relatedProducts.slice(0, 4).map((related) => (
              <ProductCard product={related} key={related.id} />
            ))}
          </div>
        </section>
      )}

      {relatedProducts.length > 4 && (
        <section className="mx-auto max-w-7xl px-6 pb-20">
          <h2 className="mb-8 text-2xl font-display text-primary">You May Also Like</h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {relatedProducts.slice(4, 8).map((related) => (
              <ProductCard product={related} key={related.id} />
            ))}
          </div>
        </section>
      )}
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
