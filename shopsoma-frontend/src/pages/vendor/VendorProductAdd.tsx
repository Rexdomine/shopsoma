import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Info, Maximize2, Trash2, ChevronDown, Upload, X, Plus, Edit2, HelpCircle, Check } from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import CollectionModal from '../../components/vendor/CollectionModal';
import ToastContainer from '../../components/ui/ToastContainer';
import { ROUTES } from '../../config/constants';
import { useVendor } from '../../context/VendorContext';
import { useToast } from '../../hooks/useToast';
import { productService } from '../../services/productService';
import { categoryService } from '../../services/categoryService';
import { collectionService } from '../../services/collectionService';
import type { Variation, Category, Collection } from '../../types';

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
  const { vendorProfile } = useVendor();
  const { toasts, hideToast, success, error, warning } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Product details
  const [productName, setProductName] = useState('');
  const [productCategory, setProductCategory] = useState('');
  const [primaryCategoryId, setPrimaryCategoryId] = useState('');
  const [subcategoryId, setSubcategoryId] = useState('');
  const [productPrice, setProductPrice] = useState('');
  const [salesPrice, setSalesPrice] = useState('');
  const [productDescription, setProductDescription] = useState('');
  const [materials, setMaterials] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [color, setColor] = useState('');
  const [selectedSizes, setSelectedSizes] = useState<SizeOption[]>([]);
  const [sizingSystem, setSizingSystem] = useState<SizingSystem>('US Sizing');
  const [productCare, setProductCare] = useState('');
  const [stockAmount, setStockAmount] = useState('');

  // Category state
  const [primaryCategories, setPrimaryCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Category[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(false);

  // Collection state
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [showCollectionModal, setShowCollectionModal] = useState(false);

  // Other Details
  const [madeToOrder, setMadeToOrder] = useState(false);
  const [hasProductVariations, setHasProductVariations] = useState(false);
  const [isSustainable, setIsSustainable] = useState(false);
  const [estimatedProductionTime, setEstimatedProductionTime] = useState('');
  const [estimatedReviewTime, setEstimatedReviewTime] = useState('3 days');

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
  const [showMaterialsDropdown, setShowMaterialsDropdown] = useState(false);
  const [showCollectionDropdown, setShowCollectionDropdown] = useState(false);
  const [showColorDropdown, setShowColorDropdown] = useState(false);
  const [showSizingDropdown, setShowSizingDropdown] = useState(false);
  const [showVariationDropdown, setShowVariationDropdown] = useState(false);

  const materialOptions = ['Leather', 'Cotton', 'Wire', 'Silk', 'Wool', 'Polyester', 'Denim'];
  const colors = ['Black', 'White', 'Red', 'Blue', 'Green', 'Yellow', 'Pink', 'Purple'];

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

        setPrimaryCategories(categoriesData);
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
  const handlePrimaryCategoryChange = async (categoryId: string, categoryName: string) => {
    setPrimaryCategoryId(categoryId);
    setSubcategoryId(''); // Reset subcategory
    setSubcategories([]); // Clear subcategories
    setShowPrimaryCategoryDropdown(false);

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

  const handleSubcategoryChange = (categoryId: string, categoryName: string) => {
    setSubcategoryId(categoryId);
    setProductCategory(categoryName); // Keep for backward compatibility
    setShowSubcategoryDropdown(false);
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

  const addNewVariation = () => {
    const newId = (variations.length + 1).toString();
    setVariations([...variations, { id: newId, images: [] }]);
    setCurrentVariation(newId);
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
        warning('Invalid sales price');
        return;
      }
    }

    // Check if variation images are still uploading
    const hasUnuploadedImages = variationImages.some(img => !img.uploaded);
    if (hasUnuploadedImages) {
      warning('Some images are still uploading. Please wait or remove failed images.');
      return;
    }

    if (editingVariation) {
      // Update existing variation
      setDetailedVariations(detailedVariations.map(v =>
        v.id === editingVariation.id
          ? {
              ...v,
              name: variationName,
              type: variationType,
              hasDifferentPricing: variationHasDifferentPricing,
              price: variationPrice,
              salesPrice: variationSalesPrice,
              color: variationColor,
              selectedSizes: variationSelectedSizes,
              sizeStock: variationSizeStock,
              images: variationImages
            }
          : v
      ));
      success('Variation updated successfully', 'Updated');
    } else {
      // Add new variation
      const newVariation: DetailedVariation = {
        id: Date.now().toString(),
        name: variationName,
        type: variationType,
        hasDifferentPricing: variationHasDifferentPricing,
        price: variationPrice,
        salesPrice: variationSalesPrice,
        color: variationColor,
        selectedSizes: variationSelectedSizes,
        sizeStock: variationSizeStock,
        images: variationImages,
      };
      setDetailedVariations([...detailedVariations, newVariation]);
      success('Variation added successfully', 'Added');
    }

    setShowVariationModal(false);
    setEditingVariation(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      // Prepare variations data if product has variations
      let variationsData: Variation[] | undefined;

      if (hasProductVariations && detailedVariations.length > 0) {
        // Validate that all images are uploaded
        const hasUnuploadedImages = detailedVariations.some(v =>
          v.images.some(img => !img.uploaded || !img.imageUrl)
        );

        if (hasUnuploadedImages) {
          warning('Some images are still uploading or failed to upload. Please wait or remove failed images before submitting.');
          return;
        }

        variationsData = detailedVariations.map(v => ({
          title: v.name,
          type: v.type || 'color',
          color_hex: v.color,
          price: v.hasDifferentPricing && v.price ? parseFloat(v.price) : undefined,
          sale_price: v.hasDifferentPricing && v.salesPrice ? parseFloat(v.salesPrice) : undefined,
          images: v.images.map(img => img.imageUrl!), // Use uploaded URLs
          is_active: true,
          sizes: v.selectedSizes.map(size => ({
            size,
            stock: parseInt(v.sizeStock[size] || '0')
          }))
        })) as any; // Cast to any since API input uses 'sizes' but response uses 'size_stocks'
      }

      // Validate required fields
      if (!subcategoryId) {
        warning('Please select a category for your product');
        return;
      }

      // Get main product images from the first variation (which contains product images)
      const mainProductImages = variations.find(v => v.id === '1')?.images || [];

      // Check if main product images are uploaded
      const hasUnuploadedMainImages = mainProductImages.some(img => !img.uploaded || !img.imageUrl);

      if (hasUnuploadedMainImages) {
        warning('Some product images are still uploading or failed to upload. Please wait or remove failed images before submitting.');
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
        category_id: subcategoryId,
        collection_id: collectionId || undefined,
        status: 'draft' as const,
        is_featured: false,
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

      // Navigate to products list after a short delay to show the toast
      setTimeout(() => {
        navigate(ROUTES.VENDOR_PRODUCTS);
      }, 1500);
    } catch (error: any) {
      console.error('Error creating product:', error);
      console.error('Error response:', error.response);
      console.error('Error data:', error.response?.data);

      // Extract detailed error message
      let errorMessage = 'Failed to create product. Please try again.';
      let errorTitle = 'Error Creating Product';

      if (error.response?.data) {
        if (error.response.data.detail) {
          // FastAPI validation errors
          if (Array.isArray(error.response.data.detail)) {
            // Pydantic validation errors - format nicely
            const validationErrors = error.response.data.detail
              .map((err: any) => `${err.loc.join('.')}: ${err.msg}`)
              .join(', ');
            errorMessage = validationErrors;
            errorTitle = 'Validation Error';
          } else {
            errorMessage = error.response.data.detail;
          }
        } else if (error.response.data.message) {
          errorMessage = error.response.data.message;
        }
      }

      // Show error toast
      error(errorMessage, errorTitle, 7000);
    }
  };

  const currentVar = variations.find(v => v.id === currentVariation);
  const productId = '75D83E'; // TODO: Generate from backend

  return (
    <>
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <div className="min-h-screen bg-[#F9FAFB]">
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
                  <Info className="h-5 w-5 text-gray-400" />
                </div>

                {/* Main Images Grid */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                  {currentVar?.images.map((image, index) => (
                    <div key={image.id} className="relative group aspect-square">
                      <img
                        src={image.preview}
                        alt={`Product ${index + 1}`}
                        className="w-full h-full object-cover rounded-lg"
                      />
                      {/* Upload status indicator */}
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
                      {index === 0 && (
                        <button
                          type="button"
                          className="absolute top-2 right-2 p-1.5 bg-black/50 rounded-full text-white"
                        >
                          <Maximize2 className="h-3 w-3" />
                        </button>
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

                {/* Variation Selector */}
                <div className="mb-4">
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setShowVariationDropdown(!showVariationDropdown)}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-left flex items-center justify-between hover:border-gray-300 transition"
                    >
                      <span className="text-gray-900">
                        New Variation {currentVariation}
                      </span>
                      <ChevronDown className="h-4 w-4 text-gray-400" />
                    </button>
                    {showVariationDropdown && (
                      <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                        {variations.map((v) => (
                          <button
                            key={v.id}
                            type="button"
                            onClick={() => {
                              setCurrentVariation(v.id);
                              setShowVariationDropdown(false);
                            }}
                            className={`w-full px-4 py-2.5 text-left text-sm transition ${
                              v.id === currentVariation
                                ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                : 'text-gray-700 hover:bg-gray-50'
                            }`}
                          >
                            New Variation {v.id}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Variation Images Grid (Thumbnails) */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                  {currentVar?.images.map((image) => (
                    <div key={`thumb-${image.id}`} className="aspect-square">
                      <img
                        src={image.preview}
                        alt="Variation"
                        className="w-full h-full object-cover rounded-lg"
                      />
                    </div>
                  ))}
                </div>

                {/* Action Buttons */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading}
                      className="flex items-center gap-2 px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isUploading ? (
                        <>
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          Uploading...
                        </>
                      ) : (
                        <>
                          <Maximize2 className="h-4 w-4" />
                          Upload Images
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={deleteCurrentVariation}
                      disabled={variations.length === 1}
                      className="flex items-center gap-2 px-4 py-2.5 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </button>
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
            </div>

            {/* Right Column - Product Details */}
            <div className="space-y-6">
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h3 className="text-base font-semibold text-gray-900 mb-6">Product Details</h3>

                <div className="space-y-5">
                  {/* Product Name */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Product Name
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
                                onClick={() => handlePrimaryCategoryChange(cat.id, cat.name)}
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
                                  onClick={() => handleSubcategoryChange(cat.id, cat.name)}
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
                  </div>

                  {/* Product Price & Sales Price */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Selling Price <span className="text-xs text-gray-500">(What customers pay)</span>
                      </label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                          $
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
                          $
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
                      Product Description
                    </label>
                    <textarea
                      value={productDescription}
                      onChange={(e) => setProductDescription(e.target.value)}
                      placeholder="This Product is..."
                      rows={4}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 resize-none"
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
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                      >
                        <span className={materials ? 'text-gray-900' : 'text-gray-400'}>
                          {materials || 'Leather, Cotton, Wire'}
                        </span>
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      </button>
                      {showMaterialsDropdown && (
                        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                          {materialOptions.map((mat) => (
                            <button
                              key={mat}
                              type="button"
                              onClick={() => {
                                setMaterials(mat);
                                setShowMaterialsDropdown(false);
                              }}
                              className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 transition"
                            >
                              {mat}
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
                    <p className="text-xs text-gray-500 mb-2">
                      Choose a collection to add this product to
                    </p>
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
                            : loadingCollections
                              ? 'Loading...'
                              : collections.length === 0
                                ? 'No collections - Create one below'
                                : 'Select a Collection'}
                        </span>
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      </button>
                      {showCollectionDropdown && (
                        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                          {/* Create New Collection Button */}
                          <button
                            type="button"
                            onClick={() => {
                              setShowCollectionModal(true);
                              setShowCollectionDropdown(false);
                            }}
                            className="w-full px-4 py-3 text-left text-sm font-medium text-[#105E53] hover:bg-[#105E53]/5 transition border-b border-gray-100 flex items-center gap-2"
                          >
                            <Plus className="h-4 w-4" />
                            Create New Collection
                          </button>

                          {/* Clear Selection Option */}
                          {collectionId && (
                            <button
                              type="button"
                              onClick={() => {
                                setCollectionId('');
                                setShowCollectionDropdown(false);
                              }}
                              className="w-full px-4 py-2.5 text-left text-sm text-gray-500 hover:bg-gray-50 transition border-b border-gray-100"
                            >
                              No Collection
                            </button>
                          )}

                          {/* Existing Collections */}
                          {collections.length > 0 ? (
                            collections.map((col) => (
                              <button
                                key={col.id}
                                type="button"
                                onClick={() => {
                                  setCollectionId(col.id);
                                  setShowCollectionDropdown(false);
                                }}
                                className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                  col.id === collectionId
                                    ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                    : 'text-gray-700 hover:bg-gray-50'
                                }`}
                              >
                                <div className="flex flex-col">
                                  <span>{col.name}</span>
                                  {col.description && (
                                    <span className="text-xs text-gray-500 mt-0.5">
                                      {col.description.length > 50
                                        ? `${col.description.substring(0, 50)}...`
                                        : col.description}
                                    </span>
                                  )}
                                </div>
                              </button>
                            ))
                          ) : (
                            <div className="px-4 py-3 text-sm text-gray-500 text-center">
                              No collections yet. Create your first one!
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Color */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Color
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setShowColorDropdown(!showColorDropdown)}
                        className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-left flex items-center justify-between"
                      >
                        <span className={color ? 'text-gray-900' : 'text-gray-400'}>
                          {color || 'Select an Option'}
                        </span>
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      </button>
                      {showColorDropdown && (
                        <div className="absolute z-10 w-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                          {colors.map((col) => (
                            <button
                              key={col}
                              type="button"
                              onClick={() => {
                                setColor(col);
                                setShowColorDropdown(false);
                              }}
                              className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 transition"
                            >
                              {col}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Sizing */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <label className="block text-sm font-medium text-gray-700">
                        Sizing
                      </label>
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setShowSizingDropdown(!showSizingDropdown)}
                          className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
                        >
                          {sizingSystem}
                          <ChevronDown className="h-4 w-4" />
                        </button>
                        {showSizingDropdown && (
                          <div className="absolute right-0 z-10 mt-2 bg-white border border-gray-200 rounded-lg shadow-lg min-w-[140px]">
                            {sizingSystems.map((sys) => (
                              <button
                                key={sys}
                                type="button"
                                onClick={() => {
                                  setSizingSystem(sys);
                                  setAvailableSizes(SIZE_MAPPINGS[sys]);
                                  setSelectedSizes([]); // Clear selections when changing sizing system
                                  setShowSizingDropdown(false);
                                }}
                                className={`w-full px-4 py-2.5 text-left text-sm transition ${
                                  sizingSystem === sys
                                    ? 'bg-[#105E53]/10 text-[#105E53] font-medium'
                                    : 'hover:bg-gray-50'
                                }`}
                              >
                                {sys}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {availableSizes.map((size) => (
                        <button
                          key={size}
                          type="button"
                          onClick={() => toggleSize(size)}
                          className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                            selectedSizes.includes(size)
                              ? 'bg-[#3B3B3B] text-white'
                              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
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
                      Product Care
                    </label>
                    <textarea
                      value={productCare}
                      onChange={(e) => setProductCare(e.target.value)}
                      placeholder="This Product is..."
                      rows={3}
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 resize-none"
                    />
                  </div>

                  {/* Stock Amount */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Stock Amount
                    </label>
                    <input
                      type="text"
                      value={stockAmount}
                      onChange={(e) => setStockAmount(e.target.value)}
                      placeholder="000"
                      className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    />
                  </div>
                </div>

                {/* Other Details */}
                <div className="bg-white rounded-lg border border-gray-200 p-6 mt-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Other Details</h2>

                  <div className="space-y-4">
                    {/* Made to Order */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <label className="text-sm font-medium text-gray-700">Made to Order</label>
                        <HelpCircle className="w-4 h-4 text-gray-400" />
                      </div>
                      <button
                        type="button"
                        onClick={() => setMadeToOrder(!madeToOrder)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          madeToOrder ? 'bg-[#105E53]' : 'bg-gray-200'
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            madeToOrder ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Product Variations */}
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium text-gray-700">Product Variations</label>
                      <button
                        type="button"
                        onClick={() => setHasProductVariations(!hasProductVariations)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          hasProductVariations ? 'bg-[#105E53]' : 'bg-gray-200'
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            hasProductVariations ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Sustainable */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <label className="text-sm font-medium text-gray-700">Sustainable</label>
                        <Edit2 className="w-4 h-4 text-gray-400 cursor-pointer hover:text-gray-600" />
                      </div>
                      <button
                        type="button"
                        onClick={() => setIsSustainable(!isSustainable)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          isSustainable ? 'bg-[#105E53]' : 'bg-gray-200'
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            isSustainable ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Estimated Production Time - Only show when Made to Order is enabled */}
                    {madeToOrder && (
                      <div>
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
                  </div>
                </div>

                {/* Variations Section - Only show when Product Variations is enabled */}
                {hasProductVariations && (
                  <div className="bg-white rounded-lg border border-gray-200 p-6 mt-6">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-semibold text-gray-900">Variations</h2>
                      <button
                        type="button"
                        onClick={() => {
                          setShowVariationModal(true);
                          setEditingVariation(null);
                        }}
                        className="flex items-center gap-2 px-4 py-2 bg-[#105E53] text-white text-sm font-medium rounded-lg hover:bg-[#0c4c45] transition"
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
                            <input
                              type="text"
                              value={variationPrice}
                              onChange={(e) => setVariationPrice(e.target.value)}
                              placeholder="₦0.00"
                              disabled={!variationHasDifferentPricing}
                              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                              Sales Price
                            </label>
                            <input
                              type="text"
                              value={variationSalesPrice}
                              onChange={(e) => setVariationSalesPrice(e.target.value)}
                              placeholder="₦0.00"
                              disabled={!variationHasDifferentPricing}
                              className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
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
                              <>
                                <div className="w-8 h-8 border-2 border-gray-400 border-t-[#105E53] rounded-full animate-spin mx-auto mb-2" />
                                <p className="text-sm text-gray-600">Uploading... {Math.round(uploadProgress)}%</p>
                              </>
                            ) : (
                              <>
                                <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                                <p className="text-sm text-gray-600">Click to upload variation images</p>
                              </>
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
                      className="w-full bg-[#105E53] text-white font-medium rounded-lg py-3 hover:bg-[#0c4c45] transition"
                    >
                      Publish for Review
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
    </>
  );
}
