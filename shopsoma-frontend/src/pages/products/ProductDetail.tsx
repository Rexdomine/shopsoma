import { useEffect, useMemo, useState, useRef, type SVGProps } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Bookmark, Minus, Plus, X } from 'lucide-react';
import type { Product, ProductVariant, SizeGuide } from '../../types';
import { productService } from '../../services/productService';
import { wishlistService } from '../../services/wishlistService';
import Loading from '../../components/common/Loading';
import ProductCard from '../../components/products/ProductCard';
import { IMAGE_CONFIG, ROUTES, STORAGE_KEYS } from '../../config/constants';
import Layout from '../../components/layout/Layout';
import AddToBagModal from '../../components/modals/AddToBagModal';
import { useCartStore } from '../../store/cartStore';
import { formatPriceWithConversion } from '../../utils/pricing';
import { useCurrencyStore } from '../../store/currencyStore';
import { hasSolidColorHex, normalizeColorValue } from '../../utils/colorDisplay';
import { getOptimizedImageUrl, getProductImageSources } from '../../utils/productImages';

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
  thumbnailSrc?: string;
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
  const location = useLocation();
  const returnUrl = (location.state as { from?: string } | null)?.from;

  const handleBack = () => {
    if (returnUrl) {
      navigate(returnUrl);
    } else if (window.history.state && typeof window.history.state.idx === 'number' && window.history.state.idx > 0) {
      navigate(-1);
    } else {
      navigate(ROUTES.PRODUCTS);
    }
  };

  const addItem = useCartStore((state) => state.addItem);
  const cartError = useCartStore((state) => state.error);
  const { currentCurrency: preferredCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();

  const [product, setProduct] = useState<Product | null>(null);
  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [isImageLoading, setIsImageLoading] = useState(false);
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
  const heroImageRef = useRef<HTMLImageElement>(null);

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
        setSelectedImage(getProductImageSources(data, 'high')[0]?.src ?? null);

        // Reset selections when product changes
        setSelectedColor(null);
        setSelectedSize(null);
        setQuantity(1);

        // Auto-select variation and size for variable products or fallback to single
        if (data.variations && data.variations.length > 0) {
          const firstActive = data.variations.find((v) => v.is_active !== false) || data.variations[0];
          if (firstActive) {
            setSelectedColor(firstActive.title);
            if (firstActive.size_stocks && firstActive.size_stocks.length > 0) {
              setSelectedSize(firstActive.size_stocks[0].size);
            }
            if (firstActive.images && firstActive.images.length > 0) {
              const firstImg = getOptimizedImageUrl(firstActive.images[0], 'high').src;
              if (firstImg) {
                setSelectedImage(firstImg);
              }
            }
          }
        } else {
          const uniqueColors = getColorOptions(data.variants ?? []);
          if (uniqueColors.length === 1) {
            setSelectedColor(uniqueColors[0].value);
          }
          const uniqueSizes = getSizeOptions(data.variants ?? []);
          if (uniqueSizes.length === 1) {
            setSelectedSize(uniqueSizes[0]);
          }
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

  // Derived active variation from selectedColor or first active variation
  const selectedVariation = useMemo(() => {
    if (!product?.variations || product.variations.length === 0) return null;
    const activeVariations = product.variations.filter((v) => v.is_active !== false);
    if (!selectedColor) return activeVariations[0] || null;
    const normalizedColor = normalizeColorValue(selectedColor);
    return (
      activeVariations.find((v) => {
        const normTitle = normalizeColorValue(v.title);
        return (
          normTitle === normalizedColor ||
          normTitle.includes(normalizedColor) ||
          normalizedColor.includes(normTitle)
        );
      }) || activeVariations[0] || null
    );
  }, [product?.variations, selectedColor]);

  const colorOptions = useMemo((): ColorOption[] => {
    if (product?.variations && product.variations.length > 0) {
      return product.variations
        .filter((v) => v.is_active !== false)
        .map((v) => ({
          label: v.title,
          value: v.title,
          hex: v.color_hex ?? null,
          isSolid: hasSolidColorHex(v.color_hex),
        }));
    }
    return getColorOptions(product?.variants ?? [], selectedSize);
  }, [product?.variations, product?.variants, selectedSize]);

  const sizeOptions = useMemo(() => {
    if (selectedVariation && selectedVariation.size_stocks && selectedVariation.size_stocks.length > 0) {
      return selectedVariation.size_stocks.map((s) => s.size);
    }
    return getSizeOptions(product?.variants ?? [], selectedColor);
  }, [selectedVariation, product?.variants, selectedColor]);

  useEffect(() => {
    if (!selectedColor || colorOptions.length === 0) return;
    const normalizedSelected = normalizeColorValue(selectedColor);
    const isValid = colorOptions.some(
      (option) => normalizeColorValue(option.value) === normalizedSelected
    );
    if (!isValid && colorOptions.length > 0) {
      setSelectedColor(colorOptions[0].value);
    }
  }, [selectedColor, colorOptions]);

  useEffect(() => {
    if (sizeOptions.length > 0 && (!selectedSize || !sizeOptions.includes(selectedSize))) {
      setSelectedSize(sizeOptions[0]);
    }
  }, [sizeOptions, selectedSize]);

  // Dynamic pricing based on selected variation or product
  const { currentPrice, comparePrice } = useMemo((): { currentPrice: number; comparePrice?: number } => {
    if (selectedVariation) {
      const regPrice = selectedVariation.price != null
        ? Number(selectedVariation.price)
        : Number(product?.base_price ?? 0);
      const salePrice = selectedVariation.sale_price != null
        ? Number(selectedVariation.sale_price)
        : null;
      if (salePrice != null && salePrice > 0 && salePrice < regPrice) {
        return { currentPrice: salePrice, comparePrice: regPrice };
      }
      return {
        currentPrice: regPrice,
        comparePrice: selectedVariation.price != null
          ? undefined
          : (product?.compare_at_price ? Number(product.compare_at_price) : undefined),
      };
    }
    const isSingle = !product?.variations || product.variations.length === 0;
    return {
      currentPrice: isSingle && product?.base_price != null
        ? Number(product.base_price)
        : Number(product?.base_price ?? 0),
      comparePrice: isSingle && product?.compare_at_price != null
        ? Number(product.compare_at_price)
        : (product?.compare_at_price ? Number(product.compare_at_price) : undefined),
    };
  }, [selectedVariation, product]);

  // Inventory & stock count for current selection
  const currentSizeStock = useMemo(() => {
    if (selectedVariation && selectedVariation.size_stocks && selectedSize) {
      const match = selectedVariation.size_stocks.find(
        (s) => normalizeColorValue(s.size) === normalizeColorValue(selectedSize)
      );
      if (match) return match.stock;
    }
    return product?.total_stock ?? 0;
  }, [selectedVariation, selectedSize, product?.total_stock]);

  const usesInventoryTracking = !product?.made_to_order;
  const maxQuantity = usesInventoryTracking ? currentSizeStock : 99;
  const isOutOfStock = usesInventoryTracking ? maxQuantity <= 0 : false;

  const selectedVariant = useMemo(() => {
    const normalizeSelection = {
      color: normalizeColorValue(selectedColor || selectedVariation?.title),
      size: normalizeColorValue(selectedSize),
    };

    const variants = product?.variants ?? [];

    const match = variants.find((variant) => {
      const variantColor = normalizeColorValue(variant.color);
      const variantSize = normalizeColorValue(variant.size);
      return variantColor === normalizeSelection.color && variantSize === normalizeSelection.size;
    }) || variants.find((variant) => {
      const variantColor = normalizeColorValue(variant.color);
      return !normalizeSelection.color || variantColor === normalizeSelection.color;
    });

    if (match) {
      return {
        ...match,
        price: currentPrice,
        compare_at_price: comparePrice,
        stock: currentSizeStock,
        color: selectedVariation?.title || match.color,
        color_hex: selectedVariation?.color_hex || match.color_hex,
        size: selectedSize || match.size,
      };
    }

    if (selectedVariation) {
      const matchedSizeStock = selectedVariation.size_stocks?.find(
        (s) => normalizeColorValue(s.size) === normalizeSelection.size
      );
      return {
        id: matchedSizeStock?.id || selectedVariation.id,
        product_id: product?.id || '',
        size: selectedSize || '',
        color: selectedVariation.title,
        color_hex: selectedVariation.color_hex,
        price: currentPrice,
        compare_at_price: comparePrice,
        stock: currentSizeStock,
        is_available: !isOutOfStock,
      } as ProductVariant;
    }

    if (!product?.variants?.length && !product?.variations?.length) {
      if (!product) return null;
      return {
        id: `default-${product.id}`,
        product_id: product.id,
        price: product.base_price,
        compare_at_price: product.compare_at_price || undefined,
        stock: product.total_stock,
        is_available: product.made_to_order ? true : product.total_stock > 0,
      } as ProductVariant;
    }

    return variants[0] ?? null;
  }, [product, selectedColor, selectedSize, selectedVariation, currentPrice, comparePrice, currentSizeStock, isOutOfStock]);

  const hasInvalidSelection = useMemo(() => {
    if (!product?.variants?.length && !product?.variations?.length) return false;
    if (!selectedColor && !selectedSize) return false;
    return !selectedVariant;
  }, [product?.variants?.length, product?.variations?.length, selectedColor, selectedSize, selectedVariant]);

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

  // Get images to display:
  // If a variation is selected and has images, scope gallery to that variation's images.
  // Otherwise fall back to the product-level gallery.
  const galleryImages = useMemo((): GalleryImage[] => {
    if (!product) return [];

    if (selectedVariation && selectedVariation.images && selectedVariation.images.length > 0) {
      return selectedVariation.images.map((imgUrl, index) => {
        const high = getOptimizedImageUrl(imgUrl, 'high');
        const thumb = getOptimizedImageUrl(imgUrl, 'thumbnail');
        return {
          id: `${selectedVariation.id}-img-${index}-${imgUrl}`,
          src: high.src,
          thumbnailSrc: thumb.src,
          fallbackSrc: high.fallbackSrc || thumb.fallbackSrc,
          altText: `${product.title} - ${selectedVariation.title} ${index + 1}`,
        };
      });
    }

    const highSources = getProductImageSources(product, 'high');
    const thumbSources = getProductImageSources(product, 'thumbnail');

    return highSources.map((image, index) => ({
      id: `${product.id}-gallery-${index}-${image.src}`,
      src: image.src,
      thumbnailSrc: thumbSources[index]?.src ?? image.src,
      fallbackSrc: image.fallbackSrc,
      altText: product.title,
    }));
  }, [product, selectedVariation]);

  // When selected variation changes, switch main hero image to that variation's primary image
  useEffect(() => {
    if (!product) return;
    if (selectedVariation && selectedVariation.images && selectedVariation.images.length > 0) {
      const firstImg = getOptimizedImageUrl(selectedVariation.images[0], 'high').src;
      if (firstImg) {
        setSelectedImage(firstImg);
      }
    } else {
      const defaultImage = getProductImageSources(product, 'high')[0]?.src;
      if (defaultImage) {
        setSelectedImage(defaultImage);
      }
    }
  }, [selectedVariation?.id, product]);

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

  const heroImage = selectedImage ?? galleryImages[0]?.src ?? placeholderImage;
  const heroFallbackImage = galleryImages.find((image) => image.src === heroImage)?.fallbackSrc;

  useEffect(() => {
    // If the image is already cached/loaded in the DOM, don't show the spinner
    if (heroImageRef.current?.complete && heroImageRef.current?.naturalWidth > 0) {
      setIsImageLoading(false);
      return;
    }

    setIsImageLoading(true);

    // Safety timeout: ensure spinner never gets stuck indefinitely
    const timer = window.setTimeout(() => {
      setIsImageLoading(false);
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [heroImage]);

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
      <div className="mx-auto max-w-7xl px-4 sm:px-6 pt-6 pb-2">
        <button
          type="button"
          onClick={handleBack}
          className="inline-flex items-center gap-2 text-xs font-ui uppercase tracking-[0.2em] text-primary/70 hover:text-primary transition"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back</span>
        </button>
      </div>
      <main className="mx-auto flex max-w-7xl flex-col gap-8 sm:gap-10 px-4 sm:px-6 py-4 sm:py-6 md:flex-row md:gap-12 lg:py-8">
        <div className="md:w-1/2">
          <div className="relative aspect-[4/5] w-full overflow-hidden bg-[#f5f7f8]">
            {isImageLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-[#f5f7f8] animate-pulse z-10">
                <div className="h-8 w-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
              </div>
            )}
            <div className="flex h-full w-full items-center justify-center lg:justify-end">
              <div className="h-full w-full">
                <img
                  ref={heroImageRef}
                  src={heroImage}
                  alt={product.title}
                  className={`h-full w-full object-contain object-center transition-opacity duration-300 ${
                    isImageLoading ? 'opacity-0' : 'opacity-100'
                  }`}
                  onLoad={() => setIsImageLoading(false)}
                  onError={(event) => {
                    setIsImageLoading(false);
                    handleProductImageError(event, heroFallbackImage);
                  }}
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
                      src={image.thumbnailSrc || image.src}
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
              <h1 className="mt-2 text-2xl sm:text-3xl font-display font-medium leading-tight text-primary md:text-4xl break-words">
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
            {colorOptions.length > 0 && (
              <div>
                <div className="mb-3 flex items-center justify-between gap-4">
                  <span className="font-ui text-sm uppercase tracking-[0.18em] text-primary/60">
                    {product.product_type === 'variable' ? 'Variation:' : 'Color:'}
                  </span>
                  {(selectedColor || selectedVariation?.title) && (
                    <span className="font-ui text-xs font-bold uppercase tracking-[0.2em] text-primary">
                      {selectedColor || selectedVariation?.title}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2.5">
                  {colorOptions.map((option) => {
                    const isSelected = (selectedColor || selectedVariation?.title) === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setSelectedColor(option.value)}
                        title={option.label}
                        className={`transition relative ${
                          option.isSolid
                            ? `h-11 w-11 rounded-full border-2 p-0.5 ${
                                isSelected
                                  ? 'border-primary ring-2 ring-primary ring-offset-2'
                                  : 'border-primary/20 hover:border-primary/50'
                              }`
                            : `border px-4 py-2 font-ui text-xs uppercase tracking-[0.12em] ${
                                isSelected
                                  ? 'border-primary bg-primary text-white ring-2 ring-primary ring-offset-1'
                                  : 'border-primary/20 text-primary hover:border-primary/50'
                              }`
                        }`}
                        aria-label={`Select variation ${option.label}`}
                      >
                        {option.isSolid ? (
                          <span
                            className="block h-full w-full rounded-full border border-black/10"
                            style={{ backgroundColor: option.hex ?? '#f5f5f5' }}
                          />
                        ) : (
                          option.label
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {sizeOptions.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-ui text-xs uppercase tracking-[0.18em] text-primary/60">
                    Size:
                  </span>
                  {usesInventoryTracking && (
                    <span className="font-ui text-xs text-primary/60">
                      {isOutOfStock ? (
                        <span className="text-red-600 font-medium">Out of Stock</span>
                      ) : currentSizeStock <= 5 ? (
                        <span className="text-amber-600 font-medium">Only {currentSizeStock} left</span>
                      ) : (
                        <span className="text-emerald-700 font-medium">In Stock ({currentSizeStock} available)</span>
                      )}
                    </span>
                  )}
                </div>
                <div className="relative border-b border-primary/25 pb-2" ref={sizeDropdownRef}>
                  <button
                    type="button"
                    className="flex w-full cursor-pointer items-center justify-between bg-transparent pb-2 text-left font-ui text-sm text-primary/75 transition hover:text-primary"
                    onClick={() => setSizeMenuOpen((prev) => !prev)}
                  >
                    <span>{selectedSize ? `Size: ${selectedSize}` : 'Select Size'}</span>
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
                      {sizeOptions.map((size) => {
                        const sStock = selectedVariation?.size_stocks?.find((s) => normalizeColorValue(s.size) === normalizeColorValue(size))?.stock;
                        return (
                          <button
                            key={size}
                            type="button"
                            onClick={() => {
                              setSelectedSize(size);
                              setSizeMenuOpen(false);
                            }}
                            className={`w-full px-4 py-2.5 text-left font-ui text-sm flex items-center justify-between transition ${
                              selectedSize === size
                                ? 'bg-primary/5 font-semibold text-primary'
                                : 'text-primary/75 hover:bg-primary/5 hover:text-primary'
                            }`}
                          >
                            <span>{size}</span>
                            {sStock !== undefined && usesInventoryTracking && (
                              <span className={`text-xs ${sStock <= 0 ? 'text-red-500 font-normal' : sStock <= 5 ? 'text-amber-600' : 'text-gray-400'}`}>
                                {sStock <= 0 ? 'Out of stock' : `${sStock} left`}
                              </span>
                            )}
                          </button>
                        );
                      })}
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
          <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8 sm:py-12">
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
        <section className="mx-auto max-w-7xl px-4 sm:px-6 py-8 sm:py-12">
          <h2 className="mb-8 text-2xl font-display text-primary">Shop The Look</h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {relatedProducts.slice(0, 4).map((related) => (
              <ProductCard product={related} key={related.id} />
            ))}
          </div>
        </section>
      )}

      {relatedProducts.length > 4 && (
        <section className="mx-auto max-w-7xl px-4 sm:px-6 pb-16 sm:pb-20">
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
