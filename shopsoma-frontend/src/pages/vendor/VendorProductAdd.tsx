import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Info, Trash2, ChevronDown, Upload, X, Plus, Edit2, HelpCircle, Check } from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import CollectionModal from '../../components/vendor/CollectionModal';
import ToastContainer from '../../components/ui/ToastContainer';
import { ROUTES } from '../../config/constants';
import { useToast } from '../../hooks/useToast';
import { productService } from '../../services/productService';
import { categoryService } from '../../services/categoryService';
import { collectionService } from '../../services/collectionService';
import type { Variation, Category, Collection } from '../../types';
import type { Currency } from '../../store/currencyStore';

// US Sizing: Letter sizes (XXS-XXXL)
// UK Sizing: Numeric sizes (4-22)
// EU Sizing: Numeric sizes (32-50)
type SizeOption = 'XXXL' | 'XXL' | 'XL' | 'L' | 'M' | 'S' | 'XS' | 'XXS' | '4' | '6' | '8' | '10' | '12' | '14' | '16' | '18' | '20' | '22' | '32' | '34' | '36' | '38' | '40' | '42' | '44' | '46' | '48' | '50';
type SizingSystem = 'US Sizing' | 'UK Sizing' | 'EU Sizing';

interface ProductImage {
  id: string;
  file: File;
  preview: string;
  uploaded?: boolean;
  imageUrl?: string;
  thumbnailUrl?: string;
}

interface ProductVariation {
  id: string;
  images: ProductImage[];
}

interface DetailedVariation {
  id: string;
  name: string;
  type: string;
  hasDifferentPricing: boolean;
  price: string;
  salesPrice: string;
  color: string;
  selectedSizes: SizeOption[];
  sizeStock: Record<SizeOption, string>;
  images: ProductImage[];
}

export default function VendorProductAdd() {
  const navigate = useNavigate();
  const { toasts, hideToast, success, error, warning } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Currency state (for product pricing)
  const [productCurrency, setProductCurrency] = useState<Currency>('NGN');
  const currencySymbol = productCurrency === 'NGN' ? '₦' : '$';

  // Product details
  const [productName, setProductName] = useState('');
  const [primaryCategoryId, setPrimaryCategoryId] = useState('');
  const [subcategoryId, setSubcategoryId] = useState('');
  const [childCategoryId, setChildCategoryId] = useState('');
  const [productPrice, setProductPrice] = useState('');
  const [salesPrice, setSalesPrice] = useState('');
  const [productDescription, setProductDescription] = useState('');
  const [materials, setMaterials] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [color, setColor] = useState('#000000'); // Now stores hex value
  const [colorHex, setColorHex] = useState('#000000'); // Hex input field
  const [selectedSizes, setSelectedSizes] = useState<SizeOption[]>([]);
  const [sizingSystem, setSizingSystem] = useState<SizingSystem>('US Sizing');
  const [productCare, setProductCare] = useState('');
  const [stockAmount, setStockAmount] = useState('');

  // Category state
  const [primaryCategories, setPrimaryCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Category[]>([]);
  const [childCategories, setChildCategories] = useState<Category[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(false);

  // Collection state
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [showCollectionModal, setShowCollectionModal] = useState(false);

  // Other Details
  const [productType, setProductType] = useState<'single' | 'variable'>('single');
  const [madeToOrder, setMadeToOrder] = useState(false);
  const [isSustainable, setIsSustainable] = useState(false);
  const [estimatedProductionTime, setEstimatedProductionTime] = useState('');
  const [estimatedReviewTime] = useState('3 days');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Image management
  const [variations, setVariations] = useState<ProductVariation[]>([
    { id: '1', images: [] }
  ]);
  const [currentVariation, setCurrentVariation] = useState('1');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Detailed Variations (for the modal)
  const [detailedVariations, setDetailedVariations] = useState<DetailedVariation[]>([]);
  const [showVariationModal, setShowVariationModal] = useState(false);
  const [editingVariation, setEditingVariation] = useState<DetailedVariation | null>(null);

  // Variation modal form state (controlled inputs)
  const [variationName, setVariationName] = useState('');
  const [variationType, setVariationType] = useState('');
  const [variationHasDifferentPricing, setVariationHasDifferentPricing] = useState(false);
  const [variationPrice, setVariationPrice] = useState('');
  const [variationSalesPrice, setVariationSalesPrice] = useState('');
  const [variationColor, setVariationColor] = useState('#000000');
  const [variationColorHex, setVariationColorHex] = useState('#000000');
  const [variationSelectedSizes, setVariationSelectedSizes] = useState<SizeOption[]>([]);
  const [variationSizeStock, setVariationSizeStock] = useState<Record<SizeOption, string>>({} as Record<SizeOption, string>);
  const [variationImages, setVariationImages] = useState<ProductImage[]>([]);
  const variationFileInputRef = useRef<HTMLInputElement>(null);

  // Dropdowns
  const [showPrimaryCategoryDropdown, setShowPrimaryCategoryDropdown] = useState(false);
  const [showSubcategoryDropdown, setShowSubcategoryDropdown] = useState(false);
  const [showChildCategoryDropdown, setShowChildCategoryDropdown] = useState(false);
  const [showMaterialsDropdown, setShowMaterialsDropdown] = useState(false);
  const [showCollectionDropdown, setShowCollectionDropdown] = useState(false);
  const [showSizingDropdown, setShowSizingDropdown] = useState(false);
  const [showVariationDropdown, setShowVariationDropdown] = useState(false);

  const materialOptions = ['Leather', 'Cotton', 'Wire', 'Silk', 'Wool', 'Polyester', 'Denim'];

  // E-commerce standard size mappings
  const SIZE_MAPPINGS: Record<SizingSystem, SizeOption[]> = {
    'US Sizing': ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
    'UK Sizing': ['4', '6', '8', '10', '12', '14', '16', '18', '20', '22'],
    'EU Sizing': ['32', '34', '36', '38', '40', '42', '44', '46', '48', '50']
  };

  const sizingSystems: SizingSystem[] = ['US Sizing', 'UK Sizing', 'EU Sizing'];

  // Available sizes based on selected sizing system
  const [availableSizes, setAvailableSizes] = useState<SizeOption[]>(SIZE_MAPPINGS['US Sizing']);

  // Fetch primary categories and collections on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoadingCategories(true);
        setLoadingCollections(true);

        const [categoriesData, collectionsData] = await Promise.all([
          categoryService.getPrimaryCategories(),
          collectionService.getCollections(),
        ]);

        const allowedPrimary = new Set(['men', 'women']);
        const filteredPrimary = categoriesData.filter((category) =>
          allowedPrimary.has(category.name.trim().toLowerCase())
        );

        setPrimaryCategories(filteredPrimary);
        setCollections(collectionsData);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoadingCategories(false);
        setLoadingCollections(false);
      }
    };

    fetchData();
  }, []);

  // Fetch subcategories when primary category changes
  const handlePrimaryCategoryChange = async (categoryId: string) => {
    setPrimaryCategoryId(categoryId);
    setSubcategoryId(''); // Reset subcategory
    setChildCategoryId('');
    setSubcategories([]); // Clear subcategories
    setChildCategories([]);
    setShowPrimaryCategoryDropdown(false);
    setShowChildCategoryDropdown(false);

    try {
      setLoadingCategories(true);
      const subs = await categoryService.getSubcategories(categoryId);
      setSubcategories(subs);
    } catch (error) {
      console.error('Error fetching subcategories:', error);
    } finally {
      setLoadingCategories(false);
    }
  };

  const handleSubcategoryChange = async (categoryId: string) => {
    setSubcategoryId(categoryId);
    setChildCategoryId('');
    setChildCategories([]);
    setShowSubcategoryDropdown(false);
    setShowChildCategoryDropdown(false);

    try {
      setLoadingCategories(true);
      const children = await categoryService.getSubcategories(categoryId);
      setChildCategories(children);
    } catch (error) {
      console.error('Error fetching child categories:', error);
    } finally {
      setLoadingCategories(false);
    }
  };

  const handleChildCategoryChange = (categoryId: string) => {
    setChildCategoryId(categoryId);
    setShowChildCategoryDropdown(false);
  };

  const handleCollectionCreated = (newCollection: Collection) => {
    // Add new collection to the list
    setCollections([newCollection, ...collections]);
    // Auto-select the newly created collection
    setCollectionId(newCollection.id);
  };

  // Populate variation form when editing
  useEffect(() => {
    if (editingVariation) {
      setVariationName(editingVariation.name);
      setVariationType(editingVariation.type);
      setVariationHasDifferentPricing(editingVariation.hasDifferentPricing);
      setVariationPrice(editingVariation.price);
      setVariationSalesPrice(editingVariation.salesPrice);
      setVariationColor(editingVariation.color);
      setVariationColorHex(editingVariation.color);
      setVariationSelectedSizes(editingVariation.selectedSizes);
      setVariationSizeStock(editingVariation.sizeStock);
      setVariationImages(editingVariation.images);
    } else {
      // Reset form for new variation
      setVariationName('');
      setVariationType('');
      setVariationHasDifferentPricing(false);
      setVariationPrice('');
      setVariationSalesPrice('');
      setVariationColor('#000000');
      setVariationColorHex('#000000');
      setVariationSelectedSizes([]);
      setVariationSizeStock({} as Record<SizeOption, string>);
      setVariationImages([]);
    }
  }, [editingVariation, showVariationModal]);

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const currentVar = variations.find(v => v.id === currentVariation);
    if (!currentVar) return;

    // Validate file types before uploading
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    const invalidFiles = Array.from(files).filter(file => !allowedTypes.includes(file.type));

    if (invalidFiles.length > 0) {
      error(
        `These file types are not supported: ${invalidFiles.map(f => f.name).join(', ')}. Please use JPG, PNG, WebP, or GIF images only.`,
        'Invalid File Type',
        7000
      );

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const totalFiles = files.length;
      const newImages: ProductImage[] = [];

      for (let i = 0; i < files.length; i++) {
        const file = files[i];

        // Create preview URL for immediate display
        const preview = URL.createObjectURL(file);

        // Create temporary image object
        const tempImage: ProductImage = {
          id: Math.random().toString(36).substr(2, 9),
          file,
          preview,
          uploaded: false
        };

        newImages.push(tempImage);

        // Update progress (show upload starting)
        setUploadProgress(((i + 0.5) / totalFiles) * 100);

        try {
          // Upload image to backend
          const uploadResponse = await productService.uploadImage(file, 'products', true);

          // Update image with uploaded URLs
          tempImage.uploaded = true;
          tempImage.imageUrl = uploadResponse.original;
          tempImage.thumbnailUrl = uploadResponse.thumbnail || uploadResponse.original;

          console.log('Image uploaded successfully:', uploadResponse);
        } catch (uploadError: any) {
          console.error('Failed to upload image:', uploadError);

          // Show user-friendly error message
          let errorMsg = `Failed to upload ${file.name}`;
          if (uploadError.response?.data?.detail) {
            errorMsg = uploadError.response.data.detail;
          } else if (uploadError.message) {
            errorMsg = `${errorMsg}: ${uploadError.message}`;
          }

          // Show error toast immediately
          error(errorMsg, 'Image Upload Failed', 5000);

          // Keep the image but mark as not uploaded so we can retry or show error
          tempImage.uploaded = false;
        }

        // Update progress (upload complete)
        setUploadProgress(((i + 1) / totalFiles) * 100);
      }

      setVariations(variations.map(v =>
        v.id === currentVariation
          ? { ...v, images: [...v.images, ...newImages] }
          : v
      ));
    } finally {
      setIsUploading(false);
      setUploadProgress(0);

      // Reset file input to allow re-uploading the same files
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const removeImage = (imageId: string) => {
    // Find and revoke the object URL to free memory
    const currentVar = variations.find(v => v.id === currentVariation);
    const imageToRemove = currentVar?.images.find(img => img.id === imageId);

    if (imageToRemove?.preview) {
      URL.revokeObjectURL(imageToRemove.preview);
    }

    setVariations(variations.map(v =>
      v.id === currentVariation
        ? { ...v, images: v.images.filter(img => img.id !== imageId) }
        : v
    ));
  };

  const toggleSize = (size: SizeOption) => {
    if (selectedSizes.includes(size)) {
      setSelectedSizes(selectedSizes.filter(s => s !== size));
    } else {
      setSelectedSizes([...selectedSizes, size]);
    }
  };

  // Variation form helpers
  const toggleVariationSize = (size: SizeOption) => {
    if (variationSelectedSizes.includes(size)) {
      setVariationSelectedSizes(variationSelectedSizes.filter(s => s !== size));
    } else {
      setVariationSelectedSizes([...variationSelectedSizes, size]);
    }
  };

  const handleVariationStockChange = (size: SizeOption, value: string) => {
    setVariationSizeStock({
      ...variationSizeStock,
      [size]: value
    });
  };

  // Main product color handlers
  const handleMainColorPickerChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const colorValue = e.target.value;
    setColor(colorValue);
    setColorHex(colorValue);
  };

  const handleMainColorHexChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const hex = e.target.value;
    setColorHex(hex);
    // Only update color picker if it's a valid hex
    if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
      setColor(hex);
    }
  };

  // Variation color handlers
  const handleColorPickerChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const color = e.target.value;
    setVariationColor(color);
    setVariationColorHex(color);
  };

  const handleColorHexChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const hex = e.target.value;
    setVariationColorHex(hex);
    // Only update color picker if it's a valid hex
    if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
      setVariationColor(hex);
    }
  };

  // Variation image upload handler
  const handleVariationImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Validate file types
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    const invalidFiles = Array.from(files).filter(file => !allowedTypes.includes(file.type));

    if (invalidFiles.length > 0) {
      error(
        `These file types are not supported: ${invalidFiles.map(f => f.name).join(', ')}. Please use JPG, PNG, WebP, or GIF images only.`,
        'Invalid File Type',
        7000
      );

      if (variationFileInputRef.current) {
        variationFileInputRef.current.value = '';
      }
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const totalFiles = files.length;
      const newImages: ProductImage[] = [];

      for (let i = 0; i < files.length; i++) {
        const file = files[i];

        // Create preview URL
        const preview = URL.createObjectURL(file);

        // Create temporary image object
        const tempImage: ProductImage = {
          id: Math.random().toString(36).substr(2, 9),
          file,
          preview,
          uploaded: false
        };

        newImages.push(tempImage);

        // Update progress
        setUploadProgress(((i + 0.5) / totalFiles) * 100);

        try {
          // Upload image to backend
          const uploadResponse = await productService.uploadImage(file, 'products', true);

          // Update image with uploaded URLs
          tempImage.uploaded = true;
          tempImage.imageUrl = uploadResponse.original;
          tempImage.thumbnailUrl = uploadResponse.thumbnail || uploadResponse.original;

          console.log('Variation image uploaded successfully:', uploadResponse);
        } catch (uploadError: any) {
          console.error('Failed to upload variation image:', uploadError);

          let errorMsg = `Failed to upload ${file.name}`;
          if (uploadError.response?.data?.detail) {
            errorMsg = uploadError.response.data.detail;
          } else if (uploadError.message) {
            errorMsg = uploadError.message;
          }

          error(errorMsg, 'Upload Error', 5000);

          // Mark as failed
          tempImage.uploaded = false;
        }

        setUploadProgress(((i + 1) / totalFiles) * 100);
      }

      // Add images to variation images
      setVariationImages([...variationImages, ...newImages]);

      success(`${newImages.length} image(s) uploaded for variation`, 'Upload Complete');
    } catch (err: any) {
      console.error('Error during variation image upload:', err);
      error('Failed to upload variation images', 'Upload Error');
    } finally {
      setIsUploading(false);
      setUploadProgress(0);

      if (variationFileInputRef.current) {
        variationFileInputRef.current.value = '';
      }
    }
  };

  const removeVariationImage = (imageId: string) => {
    const imageToRemove = variationImages.find(img => img.id === imageId);

    if (imageToRemove?.preview) {
      URL.revokeObjectURL(imageToRemove.preview);
    }

    setVariationImages(variationImages.filter(img => img.id !== imageId));
  };

  // Validate and save variation
  const handleSaveVariation = () => {
    // Validation
    if (!variationName.trim()) {
      warning('Variation name is required');
      return;
    }

    if (!variationType) {
      warning('Please select a variation type');
      return;
    }

    if (variationSelectedSizes.length === 0) {
      warning('Please select at least one size');
      return;
    }

    // Validate stock values
    for (const size of variationSelectedSizes) {
      const stockValue = variationSizeStock[size];
      if (stockValue && (isNaN(parseInt(stockValue)) || parseInt(stockValue) < 0)) {
        warning(`Invalid stock value for size ${size}`);
        return;
      }
    }

    // Validate price if different pricing is enabled
    if (variationHasDifferentPricing) {
      if (variationPrice && (isNaN(parseFloat(variationPrice)) || parseFloat(variationPrice) <= 0)) {
        warning('Invalid variation price');
        return;
      }
      if (variationSalesPrice && (isNaN(parseFloat(variationSalesPrice)) || parseFloat(variationSalesPrice) <= 0)) {
        warning('Invalid variation sales price');
        return;
      }
    }

    // Create variation object
    const newVariation: DetailedVariation = {
      id: editingVariation?.id || Math.random().toString(36).substr(2, 9),
      name: variationName,
      type: variationType,
      hasDifferentPricing: variationHasDifferentPricing,
      price: variationPrice,
      salesPrice: variationSalesPrice,
      color: variationColor,
      selectedSizes: variationSelectedSizes,
      sizeStock: variationSizeStock,
      images: variationImages
    };

    if (editingVariation) {
      // Update existing variation
      setDetailedVariations(detailedVariations.map(v =>
        v.id === editingVariation.id ? newVariation : v
      ));
    } else {
      // Add new variation
      setDetailedVariations([...detailedVariations, newVariation]);
    }

    // Reset form and close modal
    setShowVariationModal(false);
    setEditingVariation(null);
  };

  // Currency handling for variations (when product currency changes)
  useEffect(() => {
    // If the product currency changes, reset variation pricing
    if (variationHasDifferentPricing) {
      setVariationPrice('');
      setVariationSalesPrice('');
    }
  }, [productCurrency]);

  // Update available sizes when sizing system changes
  useEffect(() => {
    setAvailableSizes(SIZE_MAPPINGS[sizingSystem]);
    setSelectedSizes([]); // Clear selected sizes when sizing system changes
  }, [sizingSystem]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate
    if (!productName) {
      warning('Please enter a product name');
      return;
    }
    if (!primaryCategoryId) {
      warning('Please select a primary category');
      return;
    }
    if (!subcategoryId) {
      warning('Please select a subcategory');
      return;
    }
    if (!productPrice) {
      warning('Please enter a product price');
      return;
    }
    if (!productDescription) {
      warning('Please enter a product description');
      return;
    }

    if (productType === 'variable' && detailedVariations.length > 0) {
      // Save variations data for later
    } else if (productType === 'single' && (selectedSizes.length > 0 || color)) {
      // Save single product data for later
    }

    try {
      setIsSubmitting(true);

      // Prepare images data
      const currentVar = variations.find(v => v.id === currentVariation);
      const currentVarImages = currentVar?.images ?? [];
      const images = currentVarImages
        .filter(img => img.uploaded && img.imageUrl)
        .map(img => ({ url: img.imageUrl!, thumbnail: img.thumbnailUrl }));

      const payload: any = {
        name: productName,
        description: productDescription,
        price: parseFloat(productPrice),
        sale_price: salesPrice ? parseFloat(salesPrice) : undefined,
        category_id: childCategoryId || subcategoryId || primaryCategoryId,
        primary_category_id: primaryCategoryId,
        subcategory_id: subcategoryId,
        child_category_id: childCategoryId,
        images,
        currency: productCurrency,
        is_sustainable: isSustainable,
        material: materials,
        care_instructions: productCare,
        stock: stockAmount ? parseInt(stockAmount) : undefined,
        made_to_order: madeToOrder,
        production_time: estimatedProductionTime,
        size_system: sizingSystem,
        sizes: selectedSizes,
        color,
        product_type: productType,
        detailed_variations: productType === 'variable' ? detailedVariations.map(v => ({
          name: v.name,
          variation_type: v.type,
          has_different_pricing: v.hasDifferentPricing,
          price: v.price ? parseFloat(v.price) : undefined,
          sale_price: v.salesPrice ? parseFloat(v.salesPrice) : undefined,
          color: v.color,
          sizes: v.selectedSizes,
          size_stock: v.sizeStock,
          images: v.images.filter(img => img.uploaded && img.imageUrl).map(img => ({
            url: img.imageUrl!,
            thumbnail: img.thumbnailUrl
          }))
        })) : undefined
      };

      if (collectionId) {
        payload.collection_id = collectionId;
      }

      const response = await productService.createProduct(payload);

      success('Product submitted for review successfully', 'Success');
      navigate(ROUTES.VENDOR_PRODUCTS);
    } catch (err: any) {
      console.error('Error creating product:', err);

      let errorMsg = 'Failed to create product. Please try again.';
      if (err.response?.data?.detail) {
        errorMsg = err.response.data.detail;
      }

      error(errorMsg, 'Submission Error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const productId = '75D83E'; // TODO: Generate from backend

  return (
    <div>
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <div className="min-h-screen bg-[var(--color-page-bg)]">
        <div className="flex">
          <VendorSidebar activePrimary="products" />
          <main className="flex-1 p-8">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                className="p-2 hover:bg-gray-100 rounded-lg transition"
              >
                <ArrowLeft className="h-5 w-5 text-gray-600" />
              </button>
              <div>
                <h1 className="text-2xl font-semibold text-gray-900">Add New Product</h1>
                <p className="text-sm text-gray-500 mt-1">Product ID: {productId}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {/* Currency Switcher */}
              <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
                <button
                  type="button"
                  onClick={() => setProductCurrency('USD')}
                  className={`px-4 py-2.5 text-sm font-medium transition ${
                    productCurrency === 'USD'
                      ? 'bg-[#105E53] text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  USD ($)
                </button>
                <button
                  type="button"
                  onClick={() => setProductCurrency('NGN')}
                  className={`px-4 py-2.5 text-sm font-medium transition ${
                    productCurrency === 'NGN'
                      ? 'bg-[#105E53] text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  NGN (₦)
                </button>
              </div>

              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                className="px-5 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="product-form"
                className="px-5 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0c4c45] transition"
              >
                Save Product
              </button>
            </div>
          </div>

          <form id="product-form" onSubmit={handleSubmit} className="grid grid-cols-2 gap-8">
            {/* Left Column - Image Manager */}
            <div className="space-y-6">
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold text-gray-900">Image Manager</h3>

                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        const newVariation = {
                          id: Date.now().toString(),
                          images: [] as ProductImage[]
                        };
                        setVariations([...variations, newVariation]);
                        setCurrentVariation(newVariation.id);
                      }}
                      className="flex items-center gap-2 px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0c4c45] transition"
                    >
                      <Plus className="h-4 w-4" />
                      Add Variation
                    </button>
                  </div>
                </div>

                {/* Variation Tabs */}
                <div className="flex flex-wrap gap-2 mb-6">
                  {variations.map((variation, index) => (
                    <button
                      key={variation.id}
                      type="button"
                      onClick={() => setCurrentVariation(variation.id)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                        currentVariation === variation.id
                          ? 'bg-[#105E53] text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      Variation {index + 1}
                    </button>
                  ))}
                </div>

                {/* Image Preview Grid */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  {variations.find(v => v.id === currentVariation)?.images.map((image) => (
                    <div key={image.id} className="relative group">
                      <img
                        src={image.preview}
                        alt="Product"
                        className="w-full h-32 object-cover rounded-lg"
                      />
                      <button
                        type="button"
                        onClick={() => removeImage(image.id)}
                        className="absolute top-2 right-2 p-1 bg-white/90 rounded-full opacity-0 group-hover:opacity-100 transition"
                      >
                        <X className="h-4 w-4 text-gray-600" />
                      </button>
                    </div>
                  ))}

                  {/* Upload Button */}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-gray-300 rounded-lg h-32 flex flex-col items-center justify-center text-gray-500 hover:border-[#105E53] hover:text-[#105E53] transition"
                  >
                    <Upload className="h-6 w-6 mb-2" />
                    <span className="text-sm">Add Images</span>
                  </button>
                </div>

                {/* Upload Progress & Actions */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm text-gray-500">
                    <Info className="h-4 w-4" />
                    <span>JPEG, PNG, or WEBP, max 10MB each</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading}
                      className="flex items-center gap-2 px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isUploading ? (
                        <span className="inline-flex items-center gap-2">
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          Uploading...
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          Upload Images
                        </span>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (variations.length === 1) return;
                        const updatedVariations = variations.filter(v => v.id !== currentVariation);
                        setVariations(updatedVariations);
                        setCurrentVariation(updatedVariations[0].id);
                      }}
                      disabled={variations.length === 1}
                      className="flex items-center gap-2 px-4 py-2.5 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </div>
                </div>

                {/* Upload Progress Bar */}
                {isUploading && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-gray-600">
                      <span>Uploading images...</span>
                      <span>{Math.round(uploadProgress)}%</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                      <div
                        className="h-full bg-[#105E53] rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp,image/gif"
                onChange={handleImageUpload}
                className="hidden"
              />
            </div>

            {/* Right Column - Product Details */}
            <div className="space-y-6">
              {/* Product Type Selector */}
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h3 className="text-base font-semibold text-gray-900 mb-4">Product Type</h3>

                <div className="space-y-4">
                  {/* Radio Options */}
                  <div className="flex gap-6">
                    {/* Single Product Option */}
                    <label className="flex items-start gap-3 cursor-pointer flex-1 p-4 border-2 rounded-lg transition hover:border-[#105E53]/30" style={{ borderColor: productType === 'single' ? '#105E53' : '#E5E7EB' }}>
                      <input
                        type="radio"
                        name="productType"
                        value="single"
                        checked={productType === 'single'}
                        onChange={(e) => setProductType(e.target.value as 'single' | 'variable')}
                        className="mt-1 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <div className="flex-1">
                        <div className="font-semibold text-gray-900 mb-1">Single Product</div>
                        <div className="text-sm text-gray-600">
                          Standard product with base color and size
                        </div>
                      </div>
                    </label>

                    {/* Variable Product Option */}
                    <label className="flex items-start gap-3 cursor-pointer flex-1 p-4 border-2 rounded-lg transition hover:border-[#105E53]/30" style={{ borderColor: productType === 'variable' ? '#105E53' : '#E5E7EB' }}>
                      <input
                        type="radio"
                        name="productType"
                        value="variable"
                        checked={productType === 'variable'}
                        onChange={(e) => setProductType(e.target.value as 'single' | 'variable')}
                        className="mt-1 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <div className="flex-1">
                        <div className="font-semibold text-gray-900 mb-1">Variable Product</div>
                        <div className="text-sm text-gray-600">
                          Product with multiple color/size variations
                        </div>
                      </div>
                    </label>
                  </div>

                  {/* Helper Text */}
                  {productType === 'single' ? (
                    <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800 flex items-start gap-2">
                      <svg className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      <span>Single product: Use the fields below to set base color and size. Variations section will be disabled.</span>
                    </div>
                  ) : (
                    <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg text-sm text-purple-800 flex items-start gap-2">
                      <svg className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      <span>Variable product: Add color/size variations and manage individual pricing/inventory.</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Product Details */}
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h3 className="text-base font-semibold text-gray-900 mb-4">Product Details</h3>

                <div className="space-y-4">
                  {/* Product Name */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Name *
                    </label>
                    <input
                      type="text"
                      value={productName}
                      onChange={(e) => setProductName(e.target.value)}
                      placeholder="Enter product name"
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    />
                  </div>

                  {/* Primary Category */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Primary Category *
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowPrimaryCategoryDropdown(!showPrimaryCategoryDropdown)}
                        className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      >
                        <span className={primaryCategoryId ? 'text-gray-900' : 'text-gray-500'}>
                          {primaryCategoryId
                            ? primaryCategories.find(cat => cat.id === primaryCategoryId)?.name
                            : 'Select primary category'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-500 transition ${showPrimaryCategoryDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showPrimaryCategoryDropdown && (
                        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {loadingCategories ? (
                            <div className="p-4 text-center text-sm text-gray-500">Loading...</div>
                          ) : (
                            primaryCategories.map(category => (
                              <button
                                key={category.id}
                                type="button"
                                onClick={() => handlePrimaryCategoryChange(category.id)}
                                className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
                              >
                                {category.name}
                              </button>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Subcategory */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Subcategory *
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowSubcategoryDropdown(!showSubcategoryDropdown)}
                        disabled={!primaryCategoryId}
                        className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50"
                      >
                        <span className={subcategoryId ? 'text-gray-900' : 'text-gray-500'}>
                          {subcategoryId
                            ? subcategories.find(cat => cat.id === subcategoryId)?.name
                            : 'Select subcategory'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-500 transition ${showSubcategoryDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showSubcategoryDropdown && (
                        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {loadingCategories ? (
                            <div className="p-4 text-center text-sm text-gray-500">Loading...</div>
                          ) : (
                            subcategories.map(category => (
                              <button
                                key={category.id}
                                type="button"
                                onClick={() => handleSubcategoryChange(category.id)}
                                className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
                              >
                                {category.name}
                              </button>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Child Category */}
                  {childCategories.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Child Category
                      </label>
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setShowChildCategoryDropdown(!showChildCategoryDropdown)}
                          disabled={!subcategoryId}
                          className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50"
                        >
                          <span className={childCategoryId ? 'text-gray-900' : 'text-gray-500'}>
                            {childCategoryId
                              ? childCategories.find(cat => cat.id === childCategoryId)?.name
                              : 'Select child category'}
                          </span>
                          <ChevronDown className={`w-4 h-4 text-gray-500 transition ${showChildCategoryDropdown ? 'rotate-180' : ''}`} />
                        </button>
                        {showChildCategoryDropdown && (
                          <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                            {loadingCategories ? (
                              <div className="p-4 text-center text-sm text-gray-500">Loading...</div>
                            ) : (
                              childCategories.map(category => (
                                <button
                                  key={category.id}
                                  type="button"
                                  onClick={() => handleChildCategoryChange(category.id)}
                                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
                                >
                                  {category.name}
                                </button>
                              ))
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Product Price */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Price *
                    </label>
                    <div className="relative">
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                        {currencySymbol}
                      </span>
                      <input
                        type="text"
                        value={productPrice}
                        onChange={(e) => setProductPrice(e.target.value)}
                        placeholder="0.00"
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      />
                    </div>
                  </div>

                  {/* Sales Price */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Sales Price
                    </label>
                    <div className="relative">
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                        {currencySymbol}
                      </span>
                      <input
                        type="text"
                        value={salesPrice}
                        onChange={(e) => setSalesPrice(e.target.value)}
                        placeholder="0.00"
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      />
                    </div>
                  </div>

                  {/* Product Description */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Description *
                    </label>
                    <textarea
                      value={productDescription}
                      onChange={(e) => setProductDescription(e.target.value)}
                      placeholder="Describe your product in detail"
                      rows={4}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    />
                  </div>

                  {/* Materials */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Materials
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowMaterialsDropdown(!showMaterialsDropdown)}
                        className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      >
                        <span className={materials ? 'text-gray-900' : 'text-gray-500'}>
                          {materials || 'Select material'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-500 transition ${showMaterialsDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showMaterialsDropdown && (
                        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg">
                          {materialOptions.map(material => (
                            <button
                              key={material}
                              type="button"
                              onClick={() => {
                                setMaterials(material);
                                setShowMaterialsDropdown(false);
                              }}
                              className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
                            >
                              {material}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Collection */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Collection
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowCollectionDropdown(!showCollectionDropdown)}
                        className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      >
                        <span className={collectionId ? 'text-gray-900' : 'text-gray-500'}>
                          {collectionId
                            ? collections.find(collection => collection.id === collectionId)?.name
                            : 'Select collection'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-500 transition ${showCollectionDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showCollectionDropdown && (
                        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {loadingCollections ? (
                            <div className="p-4 text-center text-sm text-gray-500">Loading...</div>
                          ) : (
                            <>
                              {collections.map(collection => (
                                <button
                                  key={collection.id}
                                  type="button"
                                  onClick={() => {
                                    setCollectionId(collection.id);
                                    setShowCollectionDropdown(false);
                                  }}
                                  className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
                                >
                                  {collection.name}
                                </button>
                              ))}
                              <button
                                type="button"
                                onClick={() => {
                                  setShowCollectionDropdown(false);
                                  setShowCollectionModal(true);
                                }}
                                className="w-full text-left px-4 py-2 text-sm text-[#105E53] hover:bg-gray-50 border-t border-gray-100"
                              >
                                + Create New Collection
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Color Selection */}
                  {productType === 'single' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Main Color
                      </label>
                      <div className="flex items-center gap-3">
                        <input
                          type="color"
                          value={color}
                          onChange={handleMainColorPickerChange}
                          className="w-12 h-12 rounded-lg border border-gray-200 cursor-pointer"
                        />
                        <input
                          type="text"
                          value={colorHex}
                          onChange={handleMainColorHexChange}
                          placeholder="#000000"
                          className="flex-1 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                    </div>
                  )}

                  {/* Sizing System */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Sizing System
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowSizingDropdown(!showSizingDropdown)}
                        className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      >
                        <span className={sizingSystem ? 'text-gray-900' : 'text-gray-500'}>
                          {sizingSystem}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-500 transition ${showSizingDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showSizingDropdown && (
                        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg">
                          {sizingSystems.map(system => (
                            <button
                              key={system}
                              type="button"
                              onClick={() => {
                                setSizingSystem(system);
                                setShowSizingDropdown(false);
                              }}
                              className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
                            >
                              {system}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Size Selection */}
                  {productType === 'single' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-3">
                        Available Sizes
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {availableSizes.map((size) => (
                          <button
                            key={size}
                            type="button"
                            className={`px-4 py-2 border rounded-lg text-sm font-medium transition ${
                              selectedSizes.includes(size)
                                ? 'bg-[#105E53] text-white border-[#105E53]'
                                : 'border-gray-300 hover:border-[#105E53] hover:bg-[#105E53]/5'
                            }`}
                            onClick={() => toggleSize(size)}
                          >
                            {size}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Stock Amount */}
                  {productType === 'single' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Stock Amount
                      </label>
                      <input
                        type="number"
                        value={stockAmount}
                        onChange={(e) => setStockAmount(e.target.value)}
                        placeholder="Enter stock amount"
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      />
                    </div>
                  )}

                  {/* Product Care */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Care Instructions
                    </label>
                    <textarea
                      value={productCare}
                      onChange={(e) => setProductCare(e.target.value)}
                      placeholder="Enter care instructions"
                      rows={3}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    />
                  </div>
                </div>
              </div>

              {/* Additional Details */}
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h3 className="text-base font-semibold text-gray-900 mb-4">Additional Details</h3>

                <div className="space-y-4">
                  {/* Made to Order */}
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={madeToOrder}
                      onChange={(e) => setMadeToOrder(e.target.checked)}
                      className="w-4 h-4 text-[#105E53] rounded border-gray-300 focus:ring-[#105E53]"
                      id="made-to-order"
                    />
                    <label htmlFor="made-to-order" className="text-sm font-medium text-gray-700">
                      Made to Order
                    </label>
                    <div className="ml-auto">
                      <HelpCircle className="w-4 h-4 text-gray-400" />
                    </div>
                  </div>

                  {/* Sustainable */}
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={isSustainable}
                      onChange={(e) => setIsSustainable(e.target.checked)}
                      className="w-4 h-4 text-[#105E53] rounded border-gray-300 focus:ring-[#105E53]"
                      id="sustainable"
                    />
                    <label htmlFor="sustainable" className="text-sm font-medium text-gray-700">
                      Sustainable
                    </label>
                    <div className="ml-auto">
                      <HelpCircle className="w-4 h-4 text-gray-400" />
                    </div>
                  </div>

                  {/* Estimated Production Time */}
                  {madeToOrder && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Estimated Production Time
                      </label>
                      <input
                        type="text"
                        value={estimatedProductionTime}
                        onChange={(e) => setEstimatedProductionTime(e.target.value)}
                        placeholder="e.g., 2-3 weeks"
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Variations Section */}
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold text-gray-900">Variations</h3>
                  {productType === 'variable' && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingVariation(null);
                        setShowVariationModal(true);
                      }}
                      className="px-3 py-1.5 text-sm font-medium text-[#105E53] border border-[#105E53] rounded-lg hover:bg-[#105E53]/5 transition"
                    >
                      Add Variation
                    </button>
                  )}
                </div>

                {productType === 'variable' ? (
                  <div>
                    {detailedVariations.length > 0 ? (
                      <div className="space-y-3">
                        {detailedVariations.map((variation) => (
                          <div
                            key={variation.id}
                            className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-gray-300 transition"
                          >
                            <div className="flex-1">
                              <div className="flex items-center gap-3">
                                <div
                                  className="w-6 h-6 rounded-full border border-gray-300"
                                  style={{ backgroundColor: variation.color }}
                                />
                                <div>
                                  <p className="font-medium text-gray-900">{variation.name}</p>
                                  <p className="text-sm text-gray-500">
                                    {variation.type} • {variation.selectedSizes.join(', ')} • Stock: {Object.values(variation.sizeStock).reduce((acc, val) => acc + (parseInt(val) || 0), 0)}
                                  </p>
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingVariation(variation);
                                  setShowVariationModal(true);
                                }}
                                className="p-2 text-gray-600 hover:text-[#105E53] transition"
                              >
                                <Edit2 className="w-4 h-4" />
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setDetailedVariations(detailedVariations.filter(v => v.id !== variation.id));
                                }}
                                className="p-2 text-gray-600 hover:text-red-600 transition"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8 text-gray-500">
                        <p className="text-sm">No variations added yet. Click "Add Variation" to create one.</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 p-8 mt-6">
                    <div className="text-center">
                      <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-200 rounded-full mb-3">
                        <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                      </div>
                      <p className="font-semibold text-gray-700 mb-2">Variations Disabled</p>
                      <p className="text-sm text-gray-600 max-w-md mx-auto">
                        Variations are only available for Variable Products. Switch to "Variable Product" above to enable this section.
                      </p>
                    </div>
                  </div>
                )}

                {/* Variation Modal */}
                {showVariationModal && (
                  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
                      <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
                        <h3 className="text-xl font-semibold text-gray-900">
                          {editingVariation ? 'Edit Variation' : 'Add Variation'}
                        </h3>
                        <button
                          type="button"
                          onClick={() => {
                            setShowVariationModal(false);
                            setEditingVariation(null);
                          }}
                          className="p-2 text-gray-400 hover:text-gray-600 transition"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      </div>

                      <div className="p-6 space-y-6">
                        {/* Variation Name */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">
                            Variation Name *
                          </label>
                          <input
                            type="text"
                            value={variationName}
                            onChange={(e) => setVariationName(e.target.value)}
                            placeholder="E.g., Red Large"
                            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                          />
                        </div>

                        {/* Variation Type */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">
                            Type *
                          </label>
                          <select
                            value={variationType}
                            onChange={(e) => setVariationType(e.target.value)}
                            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                          >
                            <option value="">Select type</option>
                            <option value="Color">Color</option>
                            <option value="Size">Size</option>
                            <option value="Material">Material</option>
                            <option value="Style">Style</option>
                          </select>
                        </div>

                        {/* Different Variation Pricing */}
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={variationHasDifferentPricing}
                            onChange={(e) => setVariationHasDifferentPricing(e.target.checked)}
                            className="w-4 h-4 text-[#105E53] rounded border-gray-300 focus:ring-[#105E53]"
                            id="variation-pricing"
                          />
                          <label htmlFor="variation-pricing" className="text-sm font-medium text-gray-700">
                            Different Variation Pricing
                          </label>
                        </div>

                        {/* Variation Price & Sales Price */}
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              Variation Price
                            </label>
                            <div className="relative">
                              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                                {currencySymbol}
                              </span>
                              <input
                                type="text"
                                value={variationPrice}
                                onChange={(e) => setVariationPrice(e.target.value)}
                                placeholder="0.00"
                                disabled={!variationHasDifferentPricing}
                                className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                              />
                            </div>
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              Sales Price
                            </label>
                            <div className="relative">
                              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                                {currencySymbol}
                              </span>
                              <input
                                type="text"
                                value={variationSalesPrice}
                                onChange={(e) => setVariationSalesPrice(e.target.value)}
                                placeholder="0.00"
                                disabled={!variationHasDifferentPricing}
                                className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                              />
                            </div>
                          </div>
                        </div>

                        {/* Color Selector */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">
                            Color Selector
                          </label>
                          <div className="flex items-center gap-3">
                            <input
                              type="color"
                              value={variationColor}
                              onChange={handleColorPickerChange}
                              className="w-12 h-12 rounded-lg border border-gray-200 cursor-pointer"
                            />
                            <input
                              type="text"
                              value={variationColorHex}
                              onChange={handleColorHexChange}
                              placeholder="#000000"
                              className="flex-1 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                            />
                          </div>
                        </div>

                        {/* Select Available Sizes */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-3">
                            Select Available Sizes *
                          </label>
                          <div className="flex flex-wrap gap-2">
                            {(['XXXL', 'XXL', 'XL', 'L', 'M', 'S', 'XS', 'XXS'] as SizeOption[]).map((size) => (
                              <button
                                key={size}
                                type="button"
                                className={`px-4 py-2 border rounded-lg text-sm font-medium transition ${
                                  variationSelectedSizes.includes(size)
                                    ? 'bg-[#105E53] text-white border-[#105E53]'
                                    : 'border-gray-300 hover:border-[#105E53] hover:bg-[#105E53]/5'
                                }`}
                                onClick={() => toggleVariationSize(size)}
                              >
                                {size}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Stock for each size */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-3">
                            Stock per Size
                          </label>
                          <div className="grid grid-cols-4 gap-3">
                            {(['XXXL', 'XXL', 'XL', 'L', 'M', 'S', 'XS', 'XXS'] as SizeOption[]).map((size) => (
                              <div key={size}>
                                <label className="block text-xs text-gray-500 mb-1">{size}</label>
                                <input
                                  type="number"
                                  min="0"
                                  placeholder="0"
                                  value={variationSizeStock[size] || ''}
                                  onChange={(e) => handleVariationStockChange(size, e.target.value)}
                                  className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                                />
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Upload Images */}
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">
                            Upload Images
                          </label>

                          {/* Hidden file input */}
                          <input
                            ref={variationFileInputRef}
                            type="file"
                            accept="image/*"
                            multiple
                            className="hidden"
                            onChange={handleVariationImageUpload}
                          />

                          {/* Image grid */}
                          {variationImages.length > 0 && (
                            <div className="grid grid-cols-4 gap-3 mb-3">
                              {variationImages.map((image) => (
                                <div key={image.id} className="relative group aspect-square">
                                  <img
                                    src={image.preview}
                                    alt="Variation"
                                    className="w-full h-full object-cover rounded-lg"
                                  />
                                  {!image.uploaded && (
                                    <div className="absolute inset-0 bg-black/50 rounded-lg flex items-center justify-center">
                                      <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                    </div>
                                  )}
                                  {image.uploaded && (
                                    <div className="absolute top-2 left-2 p-1 bg-green-500 rounded-full">
                                      <Check className="h-3 w-3 text-white" />
                                    </div>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => removeVariationImage(image.id)}
                                    className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition flex items-center justify-center rounded-lg"
                                  >
                                    <Trash2 className="h-5 w-5 text-white" />
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Upload button */}
                          <button
                            type="button"
                            onClick={() => variationFileInputRef.current?.click()}
                            disabled={isUploading}
                            className="w-full border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-[#105E53] hover:bg-[#105E53]/5 transition disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {isUploading ? (
                              <span className="inline-flex flex-col items-center gap-2">
                                <div className="w-8 h-8 border-2 border-gray-400 border-t-[#105E53] rounded-full animate-spin mx-auto mb-2" />
                                <p className="text-sm text-gray-600">Uploading... {Math.round(uploadProgress)}%</p>
                              </span>
                            ) : (
                              <span className="inline-flex flex-col items-center gap-2">
                                <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                                <p className="text-sm text-gray-600">Click to upload variation images</p>
                              </span>
                            )}
                          </button>
                        </div>

                        {/* Save Button */}
                        <button
                          type="button"
                          onClick={handleSaveVariation}
                          className="w-full bg-[#105E53] text-white py-3 rounded-lg font-medium hover:bg-[#0c4c45] transition"
                        >
                          {editingVariation ? 'Update Variation' : 'Save Variation'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Bottom Section */}
                <div className="bg-white rounded-lg border border-gray-200 p-6 mt-6">
                  <div className="text-center space-y-4">
                    <p className="text-sm text-gray-600">Estimated Review time: {estimatedReviewTime}</p>
                    <button
                      type="submit"
                      className="w-full bg-[#105E53] text-white font-medium rounded-lg py-3 hover:bg-[#0c4c45] transition inline-flex items-center justify-center gap-2 disabled:opacity-70"
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                          Publishing...
                        </span>
                      ) : (
                        'Publish for Review'
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </form>
        </main>
      </div>

      {/* Collection Modal */}
      <CollectionModal
        isOpen={showCollectionModal}
        onClose={() => setShowCollectionModal(false)}
        onCollectionCreated={handleCollectionCreated}
      />
      </div>
    </div>
  );
}
