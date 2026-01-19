import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Info, Maximize2, Trash2, ChevronDown, Upload, X, Plus, Edit2, HelpCircle, Check } from 'lucide-react';
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

  const deleteCurrentVariation = () => {
    if (variations.length === 1) return; // Don't delete the last variation
    const updatedVariations = variations.filter(v => v.id !== currentVariation);
    setVariations(updatedVariations);
    setCurrentVariation(updatedVariations[0].id);
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
      if (!variationPrice || parseFloat(variationPrice) <= 0) {
        warning('Please enter a valid price for the variation');
        return;
      }
    }

    // Create variation object
    const newVariation: DetailedVariation = {
      id: editingVariation?.id || Math.random().toString(36).substr(2, 9),
      name: variationName.trim(),
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
      setDetailedVariations(detailedVariations.map(v => v.id === editingVariation.id ? newVariation : v));
      success('Variation updated successfully');
    } else {
      // Add new variation
      setDetailedVariations([...detailedVariations, newVariation]);
      success('Variation added successfully');
    }

    // Close modal
    setShowVariationModal(false);
    setEditingVariation(null);
  };

  // Create product handler
  const handleCreateProduct = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setIsSubmitting(true);

      let variationsData: Variation[] = [];

      if (productType === 'variable') {
        // Validate variable product data
        if (detailedVariations.length === 0) {
          warning('Please add at least one variation');
          setIsSubmitting(false);
          return;
        }

        // Convert detailed variations to backend format
        variationsData = detailedVariations.map(variation => ({
          title: variation.name,
          type: variation.type.toLowerCase(),
          color_hex: variation.color,
          price: variation.hasDifferentPricing ? parseFloat(variation.price) : undefined,
          sale_price: variation.hasDifferentPricing && variation.salesPrice ? parseFloat(variation.salesPrice) : undefined,
          images: variation.images
            .filter(img => img.uploaded && img.imageUrl)
            .map(img => img.imageUrl!),
          is_active: true,
          sizes: variation.selectedSizes.map(size => ({
            size,
            stock: parseInt(variation.sizeStock[size] || '0')
          }))
        } as any));
      } else {
        // Single product - create variation from main details
        const getColorName = (hex: string) => {
          const colorMap: Record<string, string> = {
            '#000000': 'Black',
            '#FFFFFF': 'White',
            '#FF0000': 'Red',
            '#00FF00': 'Green',
            '#0000FF': 'Blue',
            '#FFFF00': 'Yellow',
            '#FFA500': 'Orange',
            '#800080': 'Purple',
            '#FFC0CB': 'Pink',
            '#A52A2A': 'Brown',
            '#808080': 'Gray',
          };

          // If exact match, return the name
          if (colorMap[hex.toUpperCase()]) {
            return colorMap[hex.toUpperCase()];
          }

          // Otherwise, approximate using the closest color
          const rgb = hex.replace('#', '').match(/.{2}/g)?.map(c => parseInt(c, 16)) || [0, 0, 0];

          let closestColor = 'Custom Color';
          let minDistance = Infinity;

          for (const [colorHex, colorName] of Object.entries(colorMap)) {
            const colorRgb = colorHex.replace('#', '').match(/.{2}/g)?.map(c => parseInt(c, 16)) || [0, 0, 0];

            const distance = Math.sqrt(
              Math.pow(rgb[0] - colorRgb[0], 2) +
              Math.pow(rgb[1] - colorRgb[1], 2) +
              Math.pow(rgb[2] - colorRgb[2], 2)
            );

            if (distance < minDistance) {
              minDistance = distance;
              closestColor = colorName;
            }
          }

          // If very close (within 50 units), use that name, otherwise "Custom Color"
          return minDistance < 50 ? closestColor : 'Custom Color';
        };

        const colorName = getColorName(colorHex);

        // Create variation with product title and color
        const variation: Variation = {
          title: `${productName} (${colorName})`,
          type: 'color',
          color_hex: colorHex,
          price: undefined, // Use product base price
          sale_price: undefined,
          images: [], // Single products use product-level images
          is_active: true,
          sizes: selectedSizes.length > 0
            ? selectedSizes.map(size => ({
                size,
                stock: parseInt(stockAmount || '0')
              }))
            : [{
                size: 'One Size' as any,
                stock: parseInt(stockAmount || '0')
              }]
        } as any;

        variationsData = [variation];
      }

      // Validate required fields
      if (!primaryCategoryId) {
        warning('Please select a primary category for your product');
        setIsSubmitting(false);
        return;
      }

      if (!subcategoryId) {
        warning('Please select a subcategory for your product');
        setIsSubmitting(false);
        return;
      }

      if (childCategories.length > 0 && !childCategoryId) {
        warning('Please select a child category for your product');
        setIsSubmitting(false);
        return;
      }

      // Get main product images from the first variation (which contains product images)
      const mainProductImages = variations.find(v => v.id === '1')?.images || [];

      // Check if main product images are uploaded
      const hasUnuploadedMainImages = mainProductImages.some(img => !img.uploaded || !img.imageUrl);

      if (hasUnuploadedMainImages) {
        warning('Some product images are still uploading or failed to upload. Please wait or remove failed images before submitting.');
        setIsSubmitting(false);
        return;
      }

      // Prepare product images array
      const productImages = mainProductImages
        .filter(img => img.uploaded && img.imageUrl)
        .map((img, index) => ({
          image_url: img.imageUrl!,
          thumbnail_url: img.thumbnailUrl || img.imageUrl!,
          alt_text: `${productName} - Image ${index + 1}`,
          display_order: index,
          is_primary: index === 0 // First image is primary
        }));

      // Prepare product data
      const productData = {
        title: productName,
        description: productDescription,
        base_price: parseFloat(productPrice),
        compare_at_price: salesPrice ? parseFloat(salesPrice) : undefined,
        total_stock: stockAmount ? parseInt(stockAmount) : 0,
        category_id: childCategoryId || subcategoryId,
        collection_id: collectionId || undefined,
        status: 'draft' as const,
        is_featured: false,
        currency: productCurrency,
        product_type: productType,
        made_to_order: madeToOrder,
        made_to_order_timeline: madeToOrder ? estimatedProductionTime : undefined,
        care_instructions: productCare || undefined,
        fabric_composition: materials || undefined,
        variations: variationsData,
        images: productImages.length > 0 ? productImages : undefined,
      };

      console.log('Creating product with data:', productData);

      // Create the product
      // Type cast as any because productImages don't have id/product_id yet (backend will generate them)
      const createdProduct = await productService.createProduct(productData as any);

      console.log('Product created successfully:', createdProduct);

      // Show success notification
      success(
        'Your product has been created and is now pending review. You can manage it in your products list.',
        'Product submitted for review successfully!'
      );

      // Reset form
      setProductName('');
      setPrimaryCategoryId('');
      setSubcategoryId('');
      setChildCategoryId('');
      setProductPrice('');
      setSalesPrice('');
      setProductDescription('');
      setMaterials('');
      setCollectionId('');
      setColor('#000000');
      setColorHex('#000000');
      setSelectedSizes([]);
      setProductCare('');
      setStockAmount('');
      setVariations([{ id: '1', images: [] }]);
      setCurrentVariation('1');
      setDetailedVariations([]);
      setShowVariationModal(false);
    } catch (err: any) {
      console.error('Error creating product:', err);
      error('Failed to create product. Please try again.', 'Error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <div className="min-h-screen bg-[var(--color-page-bg)] flex gap-8 px-8 py-6">
        <VendorSidebar activeSection="products" />

        <main className="flex-1">
          <form onSubmit={handleCreateProduct}>
            <div className="max-w-4xl">
              <div className="flex items-center gap-4 mb-6">
                <button
                  type="button"
                  onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                  className="p-2 hover:bg-white rounded-lg transition"
                >
                  <ArrowLeft className="w-5 h-5 text-gray-600" />
                </button>
                <div>
                  <h1 className="text-2xl font-display text-gray-900">Add New Product</h1>
                  <p className="text-sm text-gray-600">Create a new product listing for your store</p>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-gray-200 p-6">
                {/* Product Details Header */}
                <div className="flex items-center gap-2 mb-6">
                  <h2 className="text-lg font-display text-gray-900">Product Details</h2>
                  <Info className="w-4 h-4 text-gray-400" />
                </div>

                <div className="space-y-6">
                  {/* Product Name */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Name <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={productName}
                      onChange={(e) => setProductName(e.target.value)}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    />
                  </div>

                  {/* Product Category - Hierarchical */}
                  <div className="space-y-4">
                    {/* Primary Category */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Primary Category <span className="text-red-500">*</span>
                      </label>
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setShowPrimaryCategoryDropdown(!showPrimaryCategoryDropdown)}
                          disabled={loadingCategories}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between hover:border-gray-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <span className={primaryCategoryId ? 'text-gray-900' : 'text-gray-400'}>
                            {primaryCategoryId
                              ? primaryCategories.find(c => c.id === primaryCategoryId)?.name
                              : loadingCategories ? 'Loading...' : 'Select Primary Category'}
                          </span>
                          <ChevronDown className="h-4 w-4 text-gray-400" />
                        </button>
                        {showPrimaryCategoryDropdown && (
                          <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                            {primaryCategories.map((cat) => (
                              <button
                                key={cat.id}
                                type="button"
                                onClick={() => handlePrimaryCategoryChange(cat.id)}
                                className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                  cat.id === primaryCategoryId
                                    ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                    : 'text-gray-700 hover:bg-gray-50'
                                }`}
                              >
                                {cat.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Subcategory - Only show if primary category is selected */}
                    {primaryCategoryId && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Subcategory <span className="text-red-500">*</span>
                        </label>
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() => setShowSubcategoryDropdown(!showSubcategoryDropdown)}
                            disabled={loadingCategories || subcategories.length === 0}
                            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between hover:border-gray-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <span className={subcategoryId ? 'text-gray-900' : 'text-gray-400'}>
                              {subcategoryId
                                ? subcategories.find(c => c.id === subcategoryId)?.name
                                : loadingCategories
                                  ? 'Loading...'
                                  : subcategories.length === 0
                                    ? 'No subcategories available'
                                    : 'Select Subcategory'}
                            </span>
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                          </button>
                          {showSubcategoryDropdown && (
                            <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                              {subcategories.map((cat) => (
                                <button
                                  key={cat.id}
                                  type="button"
                                  onClick={() => handleSubcategoryChange(cat.id)}
                                  className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                    cat.id === subcategoryId
                                      ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                      : 'text-gray-700 hover:bg-gray-50'
                                  }`}
                                >
                                  {cat.name}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Child Category - Only show if subcategory has children */}
                    {subcategoryId && childCategories.length > 0 && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Child Category <span className="text-red-500">*</span>
                        </label>
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() => setShowChildCategoryDropdown(!showChildCategoryDropdown)}
                            disabled={loadingCategories || childCategories.length === 0}
                            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between hover:border-gray-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <span className={childCategoryId ? 'text-gray-900' : 'text-gray-400'}>
                              {childCategoryId
                                ? childCategories.find(c => c.id === childCategoryId)?.name
                                : loadingCategories
                                  ? 'Loading...'
                                  : childCategories.length === 0
                                    ? 'No child categories available'
                                    : 'Select Child Category'}
                            </span>
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                          </button>
                          {showChildCategoryDropdown && (
                            <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                              {childCategories.map((cat) => (
                                <button
                                  key={cat.id}
                                  type="button"
                                  onClick={() => handleChildCategoryChange(cat.id)}
                                  className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                    cat.id === childCategoryId
                                      ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                      : 'text-gray-700 hover:bg-gray-50'
                                  }`}
                                >
                                  {cat.name}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Product Price & Sales Price */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Selling Price <span className="text-xs text-gray-500">(What customers pay)</span>
                      </label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                          {currencySymbol}
                        </span>
                        <input
                          type="text"
                          value={productPrice}
                          onChange={(e) => setProductPrice(e.target.value)}
                          placeholder="000"
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Compare At Price <span className="text-xs text-gray-500">(Optional - original price for comparison)</span>
                      </label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                          {currencySymbol}
                        </span>
                        <input
                          type="text"
                          value={salesPrice}
                          onChange={(e) => setSalesPrice(e.target.value)}
                          placeholder="000"
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                      <p className="mt-1.5 text-xs text-gray-500">
                        Set a higher price to show as crossed out (e.g., was $100, now $80). Must be ≥ selling price.
                      </p>
                    </div>
                  </div>

                  {/* Product Description */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Description <span className="text-red-500">*</span>
                    </label>
                    <textarea
                      value={productDescription}
                      onChange={(e) => setProductDescription(e.target.value)}
                      rows={6}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="Tell customers about your product..."
                    />
                  </div>

                  {/* Product Type */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Type <span className="text-red-500">*</span>
                    </label>
                    <div className="flex gap-3">
                      <button
                        type="button"
                        onClick={() => setProductType('single')}
                        className={`flex-1 py-3 rounded-lg border text-sm font-medium transition ${
                          productType === 'single'
                            ? 'border-[#105E53] bg-[#105E53]/10 text-[#105E53]'
                            : 'border-gray-200 text-gray-600 hover:border-gray-300'
                        }`}
                      >
                        Single Product
                      </button>
                      <button
                        type="button"
                        onClick={() => setProductType('variable')}
                        className={`flex-1 py-3 rounded-lg border text-sm font-medium transition ${
                          productType === 'variable'
                            ? 'border-[#105E53] bg-[#105E53]/10 text-[#105E53]'
                            : 'border-gray-200 text-gray-600 hover:border-gray-300'
                        }`}
                      >
                        Variable Product
                      </button>
                    </div>
                  </div>

                  {/* Product Images */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Images <span className="text-red-500">*</span>
                    </label>

                    {/* Upload area */}
                    <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        className="hidden"
                        onChange={handleImageUpload}
                      />

                      {isUploading ? (
                        <div className="space-y-2">
                          <div className="w-12 h-12 mx-auto border-4 border-gray-200 border-t-[#105E53] rounded-full animate-spin" />
                          <p className="text-sm text-gray-600">Uploading... {Math.round(uploadProgress)}%</p>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <Upload className="w-12 h-12 text-gray-400 mx-auto" />
                          <div>
                            <button
                              type="button"
                              onClick={() => fileInputRef.current?.click()}
                              className="text-[#105E53] hover:text-[#0c4c45] font-medium"
                            >
                              Click to upload
                            </button>
                            <span className="text-gray-500"> or drag and drop</span>
                          </div>
                          <p className="text-xs text-gray-500">PNG, JPG, GIF up to 10MB each</p>
                        </div>
                      )}
                    </div>

                    {/* Image preview */}
                    {variations.find(v => v.id === currentVariation)?.images.length > 0 && (
                      <div className="grid grid-cols-4 gap-4 mt-4">
                        {variations.find(v => v.id === currentVariation)?.images.map((image) => (
                          <div key={image.id} className="relative group">
                            <div className="aspect-square rounded-lg overflow-hidden bg-gray-100">
                              <img src={image.preview} alt="Product" className="w-full h-full object-cover" />
                            </div>
                            <button
                              type="button"
                              onClick={() => removeImage(image.id)}
                              className="absolute top-2 right-2 bg-white rounded-full p-1 shadow-md opacity-0 group-hover:opacity-100 transition"
                            >
                              <X className="w-4 h-4 text-gray-600" />
                            </button>
                            {!image.uploaded && (
                              <div className="absolute inset-0 bg-black/50 rounded-lg flex items-center justify-center">
                                <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Product Price & Sales Price */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Selling Price <span className="text-xs text-gray-500">(What customers pay)</span>
                      </label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                          {currencySymbol}
                        </span>
                        <input
                          type="text"
                          value={productPrice}
                          onChange={(e) => setProductPrice(e.target.value)}
                          placeholder="000"
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Compare At Price <span className="text-xs text-gray-500">(Optional - original price for comparison)</span>
                      </label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                          {currencySymbol}
                        </span>
                        <input
                          type="text"
                          value={salesPrice}
                          onChange={(e) => setSalesPrice(e.target.value)}
                          placeholder="000"
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 pl-8 pr-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                      <p className="mt-1.5 text-xs text-gray-500">
                        Set a higher price to show as crossed out (e.g., was $100, now $80). Must be ≥ selling price.
                      </p>
                    </div>
                  </div>

                  {/* Materials */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Materials <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowMaterialsDropdown(!showMaterialsDropdown)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between hover:border-gray-300 transition"
                      >
                        <span className={materials ? 'text-gray-900' : 'text-gray-400'}>
                          {materials || 'Select Material'}
                        </span>
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      </button>
                      {showMaterialsDropdown && (
                        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                          {materialOptions.map((material) => (
                            <button
                              key={material}
                              type="button"
                              onClick={() => {
                                setMaterials(material);
                                setShowMaterialsDropdown(false);
                              }}
                              className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                material === materials
                                  ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                  : 'text-gray-700 hover:bg-gray-50'
                              }`}
                            >
                              {material}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Product Details */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Color <span className="text-red-500">*</span>
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
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Stock <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="number"
                        value={stockAmount}
                        onChange={(e) => setStockAmount(e.target.value)}
                        placeholder="0"
                        min="0"
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      />
                    </div>
                  </div>

                  {/* Sizes */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Available Sizes
                    </label>
                    <div className="flex items-center gap-4 mb-4">
                      <div className="relative flex-1">
                        <button
                          type="button"
                          onClick={() => setShowSizingDropdown(!showSizingDropdown)}
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between hover:border-gray-300 transition"
                        >
                          <span className="text-gray-900">{sizingSystem}</span>
                          <ChevronDown className="h-4 w-4 text-gray-400" />
                        </button>
                        {showSizingDropdown && (
                          <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                            {sizingSystems.map((system) => (
                              <button
                                key={system}
                                type="button"
                                onClick={() => {
                                  setSizingSystem(system);
                                  setAvailableSizes(SIZE_MAPPINGS[system]);
                                  setSelectedSizes([]);
                                  setShowSizingDropdown(false);
                                }}
                                className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                  system === sizingSystem
                                    ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                    : 'text-gray-700 hover:bg-gray-50'
                                }`}
                              >
                                {system}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {availableSizes.map((size) => (
                        <button
                          key={size}
                          type="button"
                          onClick={() => toggleSize(size)}
                          className={`px-4 py-2 rounded-lg border text-sm font-medium transition ${
                            selectedSizes.includes(size)
                              ? 'bg-[#105E53] text-white border-[#105E53]'
                              : 'border-gray-200 text-gray-600 hover:border-gray-300'
                          }`}
                        >
                          {size}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Product Care */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Care Instructions <span className="text-red-500">*</span>
                    </label>
                    <textarea
                      value={productCare}
                      onChange={(e) => setProductCare(e.target.value)}
                      rows={4}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="E.g., Dry clean only, Hand wash in cold water, etc."
                    />
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
                        disabled={loadingCollections}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between hover:border-gray-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <span className={collectionId ? 'text-gray-900' : 'text-gray-400'}>
                          {collectionId
                            ? collections.find(c => c.id === collectionId)?.name
                            : loadingCollections ? 'Loading...' : 'Select Collection'}
                        </span>
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      </button>
                      {showCollectionDropdown && (
                        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                          {collections.map((collection) => (
                            <button
                              key={collection.id}
                              type="button"
                              onClick={() => {
                                setCollectionId(collection.id);
                                setShowCollectionDropdown(false);
                              }}
                              className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                collection.id === collectionId
                                  ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                  : 'text-gray-700 hover:bg-gray-50'
                              }`}
                            >
                              {collection.name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowCollectionModal(true)}
                      className="mt-2 inline-flex items-center gap-2 text-sm text-[#105E53] hover:text-[#0c4c45] font-medium"
                    >
                      <Plus className="w-4 h-4" />
                      Create new collection
                    </button>
                  </div>

                  {/* Additional Options */}
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={madeToOrder}
                        onChange={(e) => setMadeToOrder(e.target.checked)}
                        className="rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <label className="text-sm font-medium text-gray-700">
                        Made to Order
                      </label>
                    </div>

                    {madeToOrder && (
                      <div className="ml-6">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Estimated Production Time
                        </label>
                        <input
                          type="text"
                          value={estimatedProductionTime}
                          onChange={(e) => setEstimatedProductionTime(e.target.value)}
                          placeholder="E.g., 2-3 weeks"
                          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                        />
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isSustainable}
                        onChange={(e) => setIsSustainable(e.target.checked)}
                        className="rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <label className="text-sm font-medium text-gray-700">
                        Sustainable Product
                      </label>
                    </div>
                  </div>
                </div>
              </div>

              {/* Variation Section */}
              <div className="mt-6">
                <div className="bg-white rounded-lg border border-gray-200 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <h2 className="text-lg font-display text-gray-900">Product Variations</h2>
                      <HelpCircle className="w-4 h-4 text-gray-400" />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-500">Variable Product only</span>
                      <button
                        type="button"
                        onClick={() => setShowVariationModal(true)}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-[#105E53] text-white text-sm font-medium rounded-lg hover:bg-[#0c4c45] transition"
                      >
                        <Plus className="w-4 h-4" />
                        Add Variation
                      </button>
                    </div>
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
              </div>

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
                      <>
                        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                        Publishing...
                      </>
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

      {/* Collection Modal */}
      <CollectionModal
        isOpen={showCollectionModal}
        onClose={() => setShowCollectionModal(false)}
        onCollectionCreated={handleCollectionCreated}
      />
      </div>
    </>
  );
}
