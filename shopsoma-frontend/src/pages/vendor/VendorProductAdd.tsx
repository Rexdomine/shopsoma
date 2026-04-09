import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Trash2, ChevronDown, Upload, X, Plus, Edit2, Check } from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import CollectionModal from '../../components/vendor/CollectionModal';
import ToastContainer from '../../components/ui/ToastContainer';
import { ROUTES } from '../../config/constants';
import { useToast } from '../../hooks/useToast';
import { productService } from '../../services/productService';
import type { CreateProductPayload } from '../../services/productService';
import { categoryService } from '../../services/categoryService';
import { collectionService } from '../../services/collectionService';
import type { Category, Collection } from '../../types';
import type { Currency } from '../../store/currencyStore';

// US Sizing: Letter sizes (XXS-XXXL)
// UK Sizing: Numeric sizes (4-22)
// EU Sizing: Numeric sizes (32-50)
type SizeOption = 'XXXL' | 'XXL' | 'XL' | 'L' | 'M' | 'S' | 'XS' | 'XXS' | '4' | '6' | '8' | '10' | '12' | '14' | '16' | '18' | '20' | '22' | '32' | '34' | '36' | '38' | '40' | '42' | '44' | '46' | '48' | '50';
type SizingSystem = 'US Sizing' | 'UK Sizing' | 'EU Sizing';
type VariationMode = 'Size' | 'Color';
type ColorMode = 'solid' | 'multi' | 'none';

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
  type: VariationMode;
  hasDifferentPricing: boolean;
  price: string;
  salesPrice: string;
  colorMode: ColorMode;
  colorLabel: string;
  colorHex: string;
  colorStock: string;
  sizingSystem: SizingSystem;
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
  const [colorMode, setColorMode] = useState<ColorMode>('solid');
  const [colorLabel, setColorLabel] = useState('');
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
  const [currentVariation] = useState('1');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Detailed Variations (for the modal)
  const [detailedVariations, setDetailedVariations] = useState<DetailedVariation[]>([]);
  const [showVariationModal, setShowVariationModal] = useState(false);
  const [editingVariation, setEditingVariation] = useState<DetailedVariation | null>(null);

  // Variation modal form state (controlled inputs)
  const [variationName, setVariationName] = useState('');
  const [variationType, setVariationType] = useState<VariationMode>('Color');
  const [variationHasDifferentPricing, setVariationHasDifferentPricing] = useState(false);
  const [variationPrice, setVariationPrice] = useState('');
  const [variationSalesPrice, setVariationSalesPrice] = useState('');
  const [variationColorMode, setVariationColorMode] = useState<ColorMode>('solid');
  const [variationColorLabel, setVariationColorLabel] = useState('');
  const [variationColor, setVariationColor] = useState('#000000');
  const [variationColorHex, setVariationColorHex] = useState('#000000');
  const [variationColorStock, setVariationColorStock] = useState('');
  const [variationSizingSystem, setVariationSizingSystem] = useState<SizingSystem>('US Sizing');
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

  const materialOptions = ['Leather', 'Cotton', 'Wire', 'Silk', 'Wool', 'Polyester', 'Denim'];
  const colorModeOptions: Array<{ value: ColorMode; label: string }> = [
    { value: 'solid', label: 'Solid Color' },
    { value: 'multi', label: 'Multi-color / Pattern' },
    { value: 'none', label: 'No Color' },
  ];

  // E-commerce standard size mappings
  const SIZE_MAPPINGS: Record<SizingSystem, SizeOption[]> = {
    'US Sizing': ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
    'UK Sizing': ['4', '6', '8', '10', '12', '14', '16', '18', '20', '22'],
    'EU Sizing': ['32', '34', '36', '38', '40', '42', '44', '46', '48', '50']
  };

  const sizingSystems: SizingSystem[] = ['US Sizing', 'UK Sizing', 'EU Sizing'];

  // Available sizes based on selected sizing system
  const availableSizes = SIZE_MAPPINGS[sizingSystem];

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
      setVariationColorMode(editingVariation.colorMode);
      setVariationColorLabel(editingVariation.colorLabel);
      setVariationColor(editingVariation.colorHex);
      setVariationColorHex(editingVariation.colorHex);
      setVariationColorStock(editingVariation.colorStock);
      setVariationSizingSystem(editingVariation.sizingSystem);
      setVariationSelectedSizes(editingVariation.selectedSizes);
      setVariationSizeStock(editingVariation.sizeStock);
      setVariationImages(editingVariation.images);
    } else {
      // Reset form for new variation
      setVariationName('');
      setVariationType('Color');
      setVariationHasDifferentPricing(false);
      setVariationPrice('');
      setVariationSalesPrice('');
      setVariationColorMode('solid');
      setVariationColorLabel('');
      setVariationColor('#000000');
      setVariationColorHex('#000000');
      setVariationColorStock('');
      setVariationSizingSystem('US Sizing');
      setVariationSelectedSizes([]);
      setVariationSizeStock({} as Record<SizeOption, string>);
      setVariationImages([]);
    }
  }, [editingVariation, showVariationModal]);

  useEffect(() => {
    if (variationType === 'Color') {
      setVariationSelectedSizes([]);
      setVariationSizeStock({} as Record<SizeOption, string>);
      return;
    }
    setVariationColorMode('solid');
    setVariationColorLabel('');
    setVariationColor('#000000');
    setVariationColorHex('#000000');
    setVariationColorStock('');
  }, [variationType]);

  useEffect(() => {
    if (colorMode === 'none') {
      setColorLabel('No color');
      return;
    }

    if (colorLabel === 'No color') {
      setColorLabel('');
    }
  }, [colorMode, colorLabel]);

  useEffect(() => {
    if (variationType !== 'Color') {
      return;
    }

    if (variationColorMode === 'solid') {
      return;
    }

    if (variationColorMode === 'multi') {
      if (!variationColorLabel.trim()) {
        setVariationColorLabel('Multi-color');
      }
    } else {
      setVariationColorLabel('No color');
    }

    setVariationColor('#000000');
    setVariationColorHex('#000000');
  }, [variationColorMode, variationColorLabel, variationType]);

  const getResolvedColorLabel = (mode: ColorMode, label: string) => {
    if (mode === 'none') {
      return 'No color';
    }
    if (mode === 'multi') {
      return label.trim() || 'Multi-color';
    }
    return label.trim();
  };

  useEffect(() => {
    if (!madeToOrder) {
      return;
    }
    setStockAmount('');
    setVariationColorStock('');
    setVariationSizeStock({} as Record<SizeOption, string>);
  }, [madeToOrder]);

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
    if (variationType === 'Size' && !variationName.trim()) {
      warning('Variation name is required');
      return;
    }

    if (variationType === 'Size') {
      if (variationSelectedSizes.length === 0) {
        warning('Please select at least one size');
        return;
      }

      if (!madeToOrder) {
        for (const size of variationSelectedSizes) {
          const stockValue = variationSizeStock[size];
          if (stockValue && (isNaN(parseInt(stockValue)) || parseInt(stockValue) < 0)) {
            warning(`Invalid stock value for size ${size}`);
            return;
          }
        }
      }
    } else {
      const resolvedVariationColorLabel = getResolvedColorLabel(variationColorMode, variationColorLabel);

      if (!resolvedVariationColorLabel) {
        warning('Please provide a color label for this variation');
        return;
      }

      if (!madeToOrder && variationColorStock && (isNaN(parseInt(variationColorStock)) || parseInt(variationColorStock) < 0)) {
        warning('Invalid stock value for color');
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
        warning('Invalid sales price');
        return;
      }
    }

    // Validate images
    const hasUploadedImages = variationImages.some(img => img.uploaded && img.imageUrl);
    if (!hasUploadedImages) {
      warning('Please upload at least one image for this variation');
      return;
    }

    const newVariation: DetailedVariation = {
      id: editingVariation ? editingVariation.id : Date.now().toString(),
      name: variationType === 'Color' ? getResolvedColorLabel(variationColorMode, variationColorLabel) : variationName,
      type: variationType,
      hasDifferentPricing: variationHasDifferentPricing,
      price: variationPrice,
      salesPrice: variationSalesPrice,
      colorMode: variationColorMode,
      colorLabel: getResolvedColorLabel(variationColorMode, variationColorLabel),
      colorHex: variationColorMode === 'solid' ? variationColorHex : '#000000',
      colorStock: variationColorStock,
      sizingSystem: variationSizingSystem,
      selectedSizes: variationSelectedSizes,
      sizeStock: variationSizeStock,
      images: variationImages,
    };

    if (editingVariation) {
      setDetailedVariations(detailedVariations.map(v => v.id === editingVariation.id ? newVariation : v));
    } else {
      setDetailedVariations([...detailedVariations, newVariation]);
    }

    success(editingVariation ? 'Variation updated' : 'Variation saved');
    setShowVariationModal(false);
    setEditingVariation(null);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!productName.trim()) {
      warning('Product name is required', 'Missing info');
      return;
    }

    if (!primaryCategoryId) {
      warning('Primary category is required', 'Missing info');
      return;
    }

    if (!productDescription.trim()) {
      warning('Product description is required', 'Missing info');
      return;
    }

    if (!productPrice || Number.isNaN(Number(productPrice))) {
      warning('Product price is required', 'Missing info');
      return;
    }

    if (madeToOrder && !estimatedProductionTime.trim()) {
      warning('Estimated production time is required for made-to-order items', 'Missing info');
      return;
    }

    const resolvedSingleColorLabel = getResolvedColorLabel(colorMode, colorLabel);

    if (!resolvedSingleColorLabel) {
      warning('Please provide a color option for this product', 'Missing info');
      return;
    }

    if (productType === 'single' && selectedSizes.length === 0) {
      warning('Please select at least one size', 'Missing info');
      return;
    }

    const productImageUploads = variations.flatMap((variation) => variation.images);
    const variationImageUploads = detailedVariations.flatMap((variation) => variation.images);

    if (productType === 'single' && !productImageUploads.some((image) => image.uploaded && image.imageUrl)) {
      warning('At least one product image is required', 'Missing info');
      return;
    }

    if (productType === 'variable') {
      if (detailedVariations.length === 0) {
        warning('Add at least one variation before publishing a variable product', 'Missing info');
        return;
      }

      if (!variationImageUploads.some((image) => image.uploaded && image.imageUrl)) {
        warning('At least one variation image is required', 'Missing info');
        return;
      }
    }

    setIsSubmitting(true);

    try {
      const parsedProductPrice = parseFloat(productPrice);
      const parsedSalesPrice = salesPrice ? parseFloat(salesPrice) : undefined;
      const basePrice =
        parsedSalesPrice && parsedSalesPrice > 0 && parsedSalesPrice < parsedProductPrice
          ? parsedSalesPrice
          : parsedProductPrice;
      const compareAtPrice =
        parsedSalesPrice && parsedSalesPrice > 0 && parsedSalesPrice < parsedProductPrice
          ? parsedProductPrice
          : undefined;
      const parsedStockAmount = parseInt(stockAmount || '0', 10) || 0;
      const shouldTrackStock = !madeToOrder;
      const resolvedCategoryId = childCategoryId || subcategoryId || primaryCategoryId;
      const uploadedImages =
        productType === 'single'
          ? productImageUploads.filter((image) => image.uploaded && image.imageUrl)
          : Array.from(
              new Map(
                variationImageUploads
                  .filter((image) => image.uploaded && image.imageUrl)
                  .map((image) => [image.imageUrl!, image])
              ).values()
            );

      const payload: CreateProductPayload = {
        title: productName.trim(),
        description: productDescription.trim(),
        category_id: resolvedCategoryId,
        collection_id: collectionId || undefined,
        base_price: basePrice,
        compare_at_price: compareAtPrice,
        currency: productCurrency,
        total_stock: shouldTrackStock ? parsedStockAmount : 0,
        status: 'draft',
        is_featured: false,
        product_type: productType,
        made_to_order: madeToOrder,
        made_to_order_timeline: estimatedProductionTime.trim() || undefined,
        care_instructions: productCare || undefined,
        fabric_composition: materials || undefined,
        images: uploadedImages.map((image, index) => ({
          image_url: image.imageUrl!,
          thumbnail_url: image.thumbnailUrl,
          alt_text: productName.trim() || undefined,
          display_order: index,
          is_primary: index === 0,
        })),
      };

      if (productType === 'single') {
        payload.variants = selectedSizes.map((size) => ({
          size,
          color: resolvedSingleColorLabel,
          color_hex: colorMode === 'solid' ? colorHex || undefined : undefined,
          price: basePrice,
          stock: shouldTrackStock ? parsedStockAmount : 0,
          is_available: shouldTrackStock ? parsedStockAmount > 0 : true,
        }));
      } else {
        const variantPayload: NonNullable<CreateProductPayload['variants']> = [];
        const variationPayload: NonNullable<CreateProductPayload['variations']> = [];

        detailedVariations.forEach((variation) => {
          const variationRegularPrice = variation.price ? parseFloat(variation.price) : parsedProductPrice;
          const variationSales = variation.salesPrice ? parseFloat(variation.salesPrice) : undefined;
          const variationBasePrice =
            variation.hasDifferentPricing && variationSales && variationSales > 0 && variationSales < variationRegularPrice
              ? variationSales
              : variation.hasDifferentPricing && variationRegularPrice > 0
                ? variationRegularPrice
                : basePrice;
          const variationCompareAtPrice =
            variation.hasDifferentPricing && variationSales && variationSales > 0 && variationSales < variationRegularPrice
              ? variationRegularPrice
              : undefined;

          if (variation.type === 'Color') {
            const colorStock = shouldTrackStock ? parseInt(variation.colorStock || '0', 10) || 0 : 0;
            variationPayload.push({
              title: variation.colorLabel,
              type: variation.colorMode,
              color_hex: variation.colorMode === 'solid' ? variation.colorHex || undefined : undefined,
              price: variationBasePrice,
              sale_price: variationCompareAtPrice,
              images: variation.images
                .filter((image) => image.uploaded && image.imageUrl)
                .map((image) => image.imageUrl!),
              is_active: true,
              sizes: [],
            });
            variantPayload.push({
              color: variation.colorLabel,
              color_hex: variation.colorMode === 'solid' ? variation.colorHex || undefined : undefined,
              price: variationBasePrice,
              stock: colorStock,
              is_available: shouldTrackStock ? colorStock > 0 : true,
            });
            return;
          }

          variation.selectedSizes.forEach((size) => {
            const sizeStock = shouldTrackStock ? parseInt(variation.sizeStock[size] || '0', 10) || 0 : 0;
            variantPayload.push({
              size,
              price: variationBasePrice,
              stock: sizeStock,
              is_available: shouldTrackStock ? sizeStock > 0 : true,
            });
          });
        });

        if (variationPayload.length > 0) {
          payload.variations = variationPayload;
        }
        if (variantPayload.length > 0) {
          payload.variants = variantPayload;
        }
      }

      await productService.createProduct(payload);

      success('Product submitted for review. We will notify you once it is approved.', 'Submitted');
      navigate(ROUTES.VENDOR_PRODUCTS);
    } catch (submitError: any) {
      console.error('Error creating product:', submitError);
      console.error('Error response:', submitError?.response);
      console.error('Error data:', submitError?.response?.data);

      let errorMessage = 'Failed to submit product. Please try again.';
      let errorTitle = 'Submission Failed';

      if (submitError?.response?.data) {
        if (submitError.response.data.detail) {
          if (Array.isArray(submitError.response.data.detail)) {
            errorMessage = submitError.response.data.detail.map((err: any) => err.msg).join(', ');
          } else {
            errorMessage = submitError.response.data.detail;
          }
        } else if (submitError.response.data.message) {
          errorMessage = submitError.response.data.message;
        }
      }

      // Show error toast
      error(errorMessage, errorTitle, 7000);
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentVar = variations.find(v => v.id === currentVariation);
  const currentVarImages = currentVar?.images ?? [];
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

          <form
            id="product-form"
            data-ui-version="vendor-product-add-redeploy-2026-01-20"
            onSubmit={handleSubmit}
            className="grid grid-cols-2 gap-8"
          >
            <div className="space-y-6">
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-lg font-semibold text-gray-900">Product Details</h2>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                        productType === 'single'
                          ? 'bg-[#105E53] text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                      onClick={() => setProductType('single')}
                    >
                      Single Product
                    </button>
                    <button
                      type="button"
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                        productType === 'variable'
                          ? 'bg-[#105E53] text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                      onClick={() => setProductType('variable')}
                    >
                      Variable Product
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Name *
                    </label>
                    <input
                      type="text"
                      value={productName}
                      onChange={(e) => setProductName(e.target.value)}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="Enter product name"
                      required
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="relative">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Primary Category *
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowPrimaryCategoryDropdown(!showPrimaryCategoryDropdown)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                      >
                        <span className={primaryCategoryId ? 'text-gray-900' : 'text-gray-400'}>
                          {primaryCategories.find(cat => cat.id === primaryCategoryId)?.name || 'Select category'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-400 transition ${showPrimaryCategoryDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showPrimaryCategoryDropdown && (
                        <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {loadingCategories ? (
                            <div className="p-4 text-center text-gray-500">Loading...</div>
                          ) : primaryCategories.length > 0 ? (
                            primaryCategories.map((category) => (
                              <button
                                key={category.id}
                                type="button"
                                onClick={() => handlePrimaryCategoryChange(category.id)}
                                className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                              >
                                {category.name}
                              </button>
                            ))
                          ) : (
                            <div className="p-4 text-center text-gray-500">No categories available</div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="relative">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Sub Category *
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowSubcategoryDropdown(!showSubcategoryDropdown)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                        disabled={!primaryCategoryId}
                      >
                        <span className={subcategoryId ? 'text-gray-900' : 'text-gray-400'}>
                          {subcategories.find(cat => cat.id === subcategoryId)?.name || 'Select subcategory'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-400 transition ${showSubcategoryDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showSubcategoryDropdown && (
                        <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {loadingCategories ? (
                            <div className="p-4 text-center text-gray-500">Loading...</div>
                          ) : subcategories.length > 0 ? (
                            subcategories.map((category) => (
                              <button
                                key={category.id}
                                type="button"
                                onClick={() => handleSubcategoryChange(category.id)}
                                className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                              >
                                {category.name}
                              </button>
                            ))
                          ) : (
                            <div className="p-4 text-center text-gray-500">No subcategories available</div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="relative">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Child Category
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowChildCategoryDropdown(!showChildCategoryDropdown)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                        disabled={!subcategoryId}
                      >
                        <span className={childCategoryId ? 'text-gray-900' : 'text-gray-400'}>
                          {childCategories.find(cat => cat.id === childCategoryId)?.name || 'Select child category'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-400 transition ${showChildCategoryDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showChildCategoryDropdown && (
                        <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {loadingCategories ? (
                            <div className="p-4 text-center text-gray-500">Loading...</div>
                          ) : childCategories.length > 0 ? (
                            childCategories.map((category) => (
                              <button
                                key={category.id}
                                type="button"
                                onClick={() => handleChildCategoryChange(category.id)}
                                className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                              >
                                {category.name}
                              </button>
                            ))
                          ) : (
                            <div className="p-4 text-center text-gray-500">No child categories available</div>
                          )}
                        </div>
                      )}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Collection
                      </label>
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setShowCollectionDropdown(!showCollectionDropdown)}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                        >
                          <span className={collectionId ? 'text-gray-900' : 'text-gray-400'}>
                            {collections.find(col => col.id === collectionId)?.name || 'Select collection (optional)'}
                          </span>
                          <ChevronDown className={`w-4 h-4 text-gray-400 transition ${showCollectionDropdown ? 'rotate-180' : ''}`} />
                        </button>
                        {showCollectionDropdown && (
                          <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                            {loadingCollections ? (
                              <div className="p-4 text-center text-gray-500">Loading...</div>
                            ) : collections.length > 0 ? (
                              collections.map((collection) => (
                                <button
                                  key={collection.id}
                                  type="button"
                                  onClick={() => {
                                    setCollectionId(collection.id);
                                    setShowCollectionDropdown(false);
                                  }}
                                  className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                                >
                                  {collection.name}
                                </button>
                              ))
                            ) : (
                              <div className="p-4 text-center text-gray-500">No collections available</div>
                            )}
                            <div className="border-t border-gray-200 p-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setShowCollectionDropdown(false);
                                  setShowCollectionModal(true);
                                }}
                                className="w-full px-4 py-2 text-sm text-[#105E53] hover:bg-[#105E53]/5 rounded-lg flex items-center gap-2"
                              >
                                <Plus className="w-4 h-4" />
                                Create New Collection
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

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
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        placeholder="0.00"
                        required
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
                        value={salesPrice}
                        onChange={(e) => setSalesPrice(e.target.value)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        placeholder="0.00"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Description *
                    </label>
                    <textarea
                      value={productDescription}
                      onChange={(e) => setProductDescription(e.target.value)}
                      rows={4}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="Describe your product"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Materials
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowMaterialsDropdown(!showMaterialsDropdown)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                      >
                        <span className={materials ? 'text-gray-900' : 'text-gray-400'}>
                          {materials || 'Select materials'}
                        </span>
                        <ChevronDown className={`w-4 h-4 text-gray-400 transition ${showMaterialsDropdown ? 'rotate-180' : ''}`} />
                      </button>
                      {showMaterialsDropdown && (
                        <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                          {materialOptions.map((material) => (
                            <button
                              key={material}
                              type="button"
                              onClick={() => {
                                setMaterials(material);
                                setShowMaterialsDropdown(false);
                              }}
                              className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                            >
                              {material}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Color Option *
                      </label>
                      <select
                        value={colorMode}
                        onChange={(e) => setColorMode(e.target.value as ColorMode)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      >
                        {colorModeOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {(colorMode === 'solid' || colorMode === 'multi') && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Color Label *
                        </label>
                        <input
                          type="text"
                          value={colorLabel}
                          onChange={(e) => setColorLabel(e.target.value)}
                          placeholder={colorMode === 'solid' ? 'E.g., Black' : 'E.g., Multi-color / Ankara Print'}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                    )}

                    {colorMode === 'solid' && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Solid Color Swatch
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

                    {colorMode === 'none' && (
                      <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500">
                        Customers will see this item as <span className="font-medium text-gray-700">No color</span>.
                      </p>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Estimated Production Time {madeToOrder ? '*' : ''}
                      </label>
                      <input
                        type="text"
                        value={estimatedProductionTime}
                        onChange={(e) => setEstimatedProductionTime(e.target.value)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        placeholder="E.g., 2-3 weeks"
                        required={madeToOrder}
                      />
                      {madeToOrder && (
                        <p className="mt-2 text-xs text-[#105E53]">
                          Required for made-to-order pieces so customers know the production timeline.
                        </p>
                      )}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Product Care Instructions
                      </label>
                      <input
                        type="text"
                        value={productCare}
                        onChange={(e) => setProductCare(e.target.value)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        placeholder="Care instructions"
                      />
                    </div>
                  </div>

                  {productType === 'single' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Stock Amount
                      </label>
                      <input
                        type="number"
                        min="0"
                        value={stockAmount}
                        onChange={(e) => setStockAmount(e.target.value)}
                        className={`w-full rounded-lg border px-4 py-3 text-sm transition ${
                          madeToOrder
                            ? 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                            : 'border-gray-200 bg-gray-50 focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20'
                        }`}
                        placeholder={madeToOrder ? 'Disabled for made-to-order' : '0'}
                        disabled={madeToOrder}
                      />
                      <p className="mt-2 text-xs text-gray-500">
                        {madeToOrder
                          ? 'Inventory tracking is disabled for made-to-order products. Use production time instead.'
                          : 'Use stock amount only for ready-to-ship inventory.'}
                      </p>
                    </div>
                  )}

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
                  </div>

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
                  </div>
                </div>
              </div>

              {productType === 'single' && (
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-6">Size Selection</h2>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Sizing System
                      </label>
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setShowSizingDropdown(!showSizingDropdown)}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                        >
                          <span className="text-gray-900">{sizingSystem}</span>
                          <ChevronDown className={`w-4 h-4 text-gray-400 transition ${showSizingDropdown ? 'rotate-180' : ''}`} />
                        </button>
                        {showSizingDropdown && (
                          <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg">
                            {sizingSystems.map((system) => (
                              <button
                                key={system}
                                type="button"
                                onClick={() => {
                                  setSizingSystem(system);
                                  setShowSizingDropdown(false);
                                }}
                                className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                              >
                                {system}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-3">
                        Select Available Sizes *
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
                  </div>
                </div>
              )}

            </div>

            <div className="space-y-6">
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <div className="mb-6">
                  <h2 className="text-lg font-semibold text-gray-900">Product Images</h2>
                  <p className="mt-2 text-sm text-gray-500">
                    {productType === 'single'
                      ? 'Upload the main product images that shoppers will see first.'
                      : 'Variable products use variation images only. Add images inside each variation to avoid duplicate galleries.'}
                  </p>
                </div>

                <div className="space-y-4">
                  {/* Hidden file input */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    onChange={handleImageUpload}
                  />

                  {/* Image grid */}
                  {productType === 'single' && currentVarImages.length > 0 && (
                    <div className="grid grid-cols-4 gap-3">
                      {currentVarImages.map((image) => (
                        <div key={image.id} className="relative group aspect-square">
                          <img
                            src={image.preview}
                            alt="Product"
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
                            onClick={() => removeImage(image.id)}
                            className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition flex items-center justify-center rounded-lg"
                          >
                            <Trash2 className="h-5 w-5 text-white" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Upload button */}
                  {productType === 'single' ? (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
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
                          <p className="text-sm text-gray-600">Click to upload product images</p>
                        </span>
                      )}
                    </button>
                  ) : (
                    <div className="w-full border-2 border-dashed border-gray-300 rounded-lg p-8 text-center bg-gray-50">
                      <p className="text-sm font-medium text-gray-700">Featured image disabled for variable products</p>
                      <p className="mt-2 text-sm text-gray-500">
                        Upload images inside each variation. The product gallery will be generated from those variation images.
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {productType === 'variable' ? (
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-semibold text-gray-900">Product Variations</h2>
                    <button
                      type="button"
                      onClick={() => {
                        setShowVariationModal(true);
                        setEditingVariation(null);
                      }}
                      className="px-4 py-2 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0c4c45] transition inline-flex items-center gap-2"
                    >
                      <Plus className="w-4 h-4" />
                      Add Variation
                    </button>
                  </div>

                  {/* List of existing variations */}
                  {detailedVariations.length > 0 ? (
                    <div className="space-y-3">
                      {detailedVariations.map((variation) => (
                        <div
                          key={variation.id}
                          className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-gray-300 transition"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-3">
                              {variation.type === 'Color' && variation.colorMode === 'solid' ? (
                                <div
                                  className="w-6 h-6 rounded-full border border-gray-300"
                                  style={{ backgroundColor: variation.colorHex }}
                                />
                              ) : variation.type === 'Color' ? (
                                <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-600">
                                  {variation.colorLabel}
                                </span>
                              ) : (
                                <div className="w-6 h-6 rounded-full border border-dashed border-gray-300 bg-gray-50" />
                              )}
                              <div>
                                <p className="font-medium text-gray-900">
                                  {variation.type === 'Color' ? variation.colorLabel : variation.name}
                                </p>
                                <p className="text-sm text-gray-500">
                                  {variation.type} • {variation.type === 'Size'
                                    ? `${variation.selectedSizes.join(', ')} • Stock: ${Object.values(variation.sizeStock).reduce((acc, val) => acc + (parseInt(val) || 0), 0)}`
                                    : `Stock: ${parseInt(variation.colorStock || '0', 10) || 0}`}
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
                          {variationType === 'Color' ? 'Internal Variation Name' : 'Variation Name *'}
                        </label>
                        <input
                          type="text"
                          value={variationName}
                          onChange={(e) => setVariationName(e.target.value)}
                          placeholder={variationType === 'Color' ? 'Optional internal name' : 'E.g., Red Large'}
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
                          onChange={(e) => setVariationType(e.target.value as VariationMode)}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        >
                          <option value="Color">Color</option>
                          <option value="Size">Size</option>
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
                      <div className="space-y-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">
                            Color Option
                          </label>
                          <select
                            value={variationColorMode}
                            onChange={(e) => setVariationColorMode(e.target.value as ColorMode)}
                            disabled={variationType === 'Size'}
                            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {colorModeOptions.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>

                        {variationType === 'Color' && variationColorMode !== 'none' && (
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              Color Label *
                            </label>
                            <input
                              type="text"
                              value={variationColorLabel}
                              onChange={(e) => setVariationColorLabel(e.target.value)}
                              placeholder={variationColorMode === 'solid' ? 'E.g., Black' : 'E.g., Multi-color / Mixed Print'}
                              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                            />
                          </div>
                        )}

                        {variationType === 'Color' && variationColorMode === 'solid' && (
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              Solid Color Swatch
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
                        )}

                        {variationType === 'Color' && variationColorMode === 'none' && (
                          <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500">
                            Customers will see this option as <span className="font-medium text-gray-700">No color</span>.
                          </p>
                        )}
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Stock per Color
                        </label>
                        <input
                          type="number"
                          min="0"
                          value={variationColorStock}
                          onChange={(e) => setVariationColorStock(e.target.value)}
                          disabled={variationType === 'Size' || madeToOrder}
                          placeholder={madeToOrder ? 'Disabled for made-to-order' : '0'}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        {madeToOrder && (
                          <p className="mt-2 text-xs text-gray-500">
                            Stock tracking is off for made-to-order variations.
                          </p>
                        )}
                      </div>

                      {/* Variation Sizing System */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Sizing System
                        </label>
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() => setShowSizingDropdown(!showSizingDropdown)}
                            disabled={variationType === 'Color'}
                            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <span className="text-gray-900">{variationSizingSystem}</span>
                            <ChevronDown className="w-4 h-4 text-gray-400" />
                          </button>
                          {showSizingDropdown && (
                            <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                              {sizingSystems.map((system) => (
                                <button
                                  key={system}
                                  type="button"
                                  onClick={() => {
                                    setVariationSizingSystem(system);
                                    setVariationSelectedSizes([]);
                                    setVariationSizeStock({} as Record<SizeOption, string>);
                                    setShowSizingDropdown(false);
                                  }}
                                  className="w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50"
                                >
                                  {system}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Select Available Sizes */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-3">
                          Select Available Sizes *
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {SIZE_MAPPINGS[variationSizingSystem].map((size) => (
                            <button
                              key={size}
                              type="button"
                              disabled={variationType === 'Color'}
                              className={`px-4 py-2 border rounded-lg text-sm font-medium transition ${
                                variationSelectedSizes.includes(size)
                                  ? 'bg-[#105E53] text-white border-[#105E53]'
                                  : 'border-gray-300 hover:border-[#105E53] hover:bg-[#105E53]/5'
                              } disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-gray-300 disabled:hover:bg-transparent`}
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
                          {SIZE_MAPPINGS[variationSizingSystem].map((size) => (
                            <div key={size}>
                              <label className="block text-xs text-gray-500 mb-1">{size}</label>
                              <input
                                type="number"
                                min="0"
                                placeholder="0"
                                value={variationSizeStock[size] || ''}
                                onChange={(e) => handleVariationStockChange(size, e.target.value)}
                                disabled={variationType === 'Color' || madeToOrder}
                                className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                              />
                            </div>
                          ))}
                        </div>
                        {madeToOrder && (
                          <p className="mt-2 text-xs text-gray-500">
                            Size-level inventory is disabled for made-to-order products.
                          </p>
                        )}
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
          </form>
        </main>
      </div>
    </div>

      {/* Collection Modal */}
      <CollectionModal
        isOpen={showCollectionModal}
        onClose={() => setShowCollectionModal(false)}
        onCollectionCreated={handleCollectionCreated}
      />
    </div>
  );
}
