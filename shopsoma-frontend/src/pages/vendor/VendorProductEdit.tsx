import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Loader2, Trash2, Upload, Image as ImageIcon, ShieldAlert } from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { ROUTES } from '../../config/constants';
import { productService } from '../../services/productService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import type { Product, ProductImage } from '../../types';
import { normalizeProductImageUrl } from '../../utils/productImages';

export default function VendorProductEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toasts, hideToast, error, success, warning } = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [product, setProduct] = useState<Product | null>(null);
  const [images, setImages] = useState<ProductImage[]>([]);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [deletingImageId, setDeletingImageId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [basePrice, setBasePrice] = useState('');
  const [comparePrice, setComparePrice] = useState('');
  const [stock, setStock] = useState('');
  const [status, setStatus] = useState<'draft' | 'active' | 'inactive' | 'archived'>('draft');
  const [madeToOrder, setMadeToOrder] = useState(false);
  const [productionTimeline, setProductionTimeline] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [lengthCm, setLengthCm] = useState('');
  const [widthCm, setWidthCm] = useState('');
  const [heightCm, setHeightCm] = useState('');

  useEffect(() => {
    const fetchProduct = async () => {
      if (!id) {
        error('Product ID is required', 'Error');
        navigate(ROUTES.VENDOR_PRODUCTS);
        return;
      }

      try {
        setLoading(true);
        const data = await productService.getVendorProduct(id);
        setProduct(data);

        // Pre-populate form fields
        setTitle(data.title);
        setDescription(data.description || '');
        setBasePrice(data.base_price.toString());
        setComparePrice(data.compare_at_price?.toString() || '');
        setStock(data.total_stock?.toString() || '0');
        setStatus(data.status);
        setMadeToOrder(Boolean(data.made_to_order));
        setProductionTimeline(data.made_to_order_timeline || '');
        setWeightKg(data.weight_kg?.toString() || '');
        setLengthCm(data.length_cm?.toString() || '');
        setWidthCm(data.width_cm?.toString() || '');
        setHeightCm(data.height_cm?.toString() || '');
        setImages(data.images || []);
      } catch (err: any) {
        console.error('Failed to load product', err);
        error(
          err.response?.data?.detail || 'Failed to load product',
          'Error'
        );
        navigate(ROUTES.VENDOR_PRODUCTS);
      } finally {
        setLoading(false);
      }
    };

    fetchProduct();
  }, [id, navigate, error]);

  useEffect(() => {
    if (madeToOrder) {
      setStock('');
    }
  }, [madeToOrder]);

  const isApproved = product?.moderation_status === 'approved';

  const handleDeleteImage = async (imageId: string) => {
    if (!id || isApproved) return;
    try {
      setDeletingImageId(imageId);
      await productService.deleteProductImage(id, imageId);
      setImages((prev) => prev.filter((img) => img.id !== imageId));
      success('Image removed successfully');
    } catch (err: any) {
      console.error('Failed to delete image', err);
      error(err.response?.data?.detail || 'Failed to delete image', 'Delete Failed');
    } finally {
      setDeletingImageId(null);
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !id || isApproved) return;

    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    const invalidFiles = Array.from(files).filter((file) => !allowedTypes.includes(file.type));
    if (invalidFiles.length > 0) {
      warning('Please upload JPG, PNG, WebP, or GIF images only.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    if (images.length + files.length > 10) {
      warning('A maximum of 10 images are allowed per product.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setIsUploadingImage(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const uploadRes = await productService.uploadImage(file, 'products', true);
        const newImage = await productService.addProductImage(id, {
          image_url: uploadRes.original,
          thumbnail_url: uploadRes.thumbnail || uploadRes.original,
          storage_keys: uploadRes.storage_keys,
          display_order: images.length + i,
          is_primary: images.length === 0 && i === 0,
        });
        setImages((prev) => [...prev, newImage]);
      }
      success('Image(s) uploaded successfully');
    } catch (err: any) {
      console.error('Failed to upload image', err);
      error(err.response?.data?.detail || 'Failed to upload image', 'Upload Failed');
    } finally {
      setIsUploadingImage(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!product || !id) return;

    // Validation
    if (!title.trim()) {
      warning('Product title is required');
      return;
    }

    if (!basePrice || parseFloat(basePrice) <= 0) {
      warning('Please enter a valid base price');
      return;
    }

    if (madeToOrder && !productionTimeline.trim()) {
      warning('Estimated production time is required for made-to-order items');
      return;
    }

    const parcelMeasurements = [weightKg, lengthCm, widthCm, heightCm];
    const hasParcelMeasurement = parcelMeasurements.some((value) => value.trim());
    if (
      hasParcelMeasurement &&
      !parcelMeasurements.every((value) => value.trim() && parseFloat(value) > 0)
    ) {
      warning('Enter positive values for all parcel measurements, or leave them all blank');
      return;
    }

    try {
      setSaving(true);

      const hasExistingParcelMeasurement = [
        product?.weight_kg,
        product?.length_cm,
        product?.width_cm,
        product?.height_cm,
      ].some((value) => value !== null && value !== undefined);
      const parcelUpdate = hasParcelMeasurement
        ? {
            weight_kg: parseFloat(weightKg),
            length_cm: parseFloat(lengthCm),
            width_cm: parseFloat(widthCm),
            height_cm: parseFloat(heightCm),
          }
        : hasExistingParcelMeasurement
          ? {
              weight_kg: null,
              length_cm: null,
              width_cm: null,
              height_cm: null,
            }
          : {};
      const updateData: Partial<Product> = {
        title: title.trim(),
        description: description.trim(),
        base_price: parseFloat(basePrice),
        compare_at_price: comparePrice ? parseFloat(comparePrice) : undefined,
        total_stock: madeToOrder ? 0 : stock ? parseInt(stock) : 0,
        status,
        made_to_order: madeToOrder,
        made_to_order_timeline: madeToOrder ? productionTimeline.trim() : undefined,
        ...parcelUpdate,
      };

      await productService.updateProduct(id, updateData as any);

      success(
        'Your product has been updated successfully!',
        'Product Updated'
      );

      // Navigate back to products list after short delay
      setTimeout(() => {
        navigate(ROUTES.VENDOR_PRODUCTS);
      }, 1500);
    } catch (err: any) {
      console.error('Failed to update product', err);
      error(
        err.response?.data?.detail || 'Failed to update product',
        'Update Failed'
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)]">
        <div className="flex">
          <VendorSidebar activePrimary="products" />
          <main className="flex-1 p-8">
            <div className="flex items-center justify-center py-20 text-gray-600 gap-3">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="text-sm">Loading product...</span>
            </div>
          </main>
        </div>
      </div>
    );
  }

  if (!product) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)]">
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <div className="flex">
        <VendorSidebar activePrimary="products" />

        <main className="flex-1 p-8">
          {/* Header */}
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                className="p-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 transition"
                title="Back to products"
              >
                <ArrowLeft className="h-5 w-5 text-gray-600" />
              </button>
              <div>
                <h1 className="text-3xl font-semibold text-gray-900">Edit Product</h1>
                <p className="text-sm text-gray-600 mt-1">{product.title}</p>
              </div>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="max-w-4xl">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">Basic Information</h2>
              </div>

              <div className="p-6 space-y-6">
                {/* Product Title */}
                <div>
                  <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-2">
                    Product Title *
                  </label>
                  <input
                    id="title"
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    placeholder="Enter product title"
                    required
                  />
                </div>

                {/* Description */}
                <div>
                  <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
                    Description
                  </label>
                  <textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={6}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    placeholder="Enter product description"
                  />
                </div>

                {/* Pricing Row */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label htmlFor="basePrice" className="block text-sm font-medium text-gray-700 mb-2">
                      Base Price ($) *
                    </label>
                    <input
                      id="basePrice"
                      type="number"
                      step="0.01"
                      min="0"
                      value={basePrice}
                      onChange={(e) => setBasePrice(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="0.00"
                      required
                    />
                  </div>

                  <div>
                    <label htmlFor="comparePrice" className="block text-sm font-medium text-gray-700 mb-2">
                      Compare at Price ($)
                    </label>
                    <input
                      id="comparePrice"
                      type="number"
                      step="0.01"
                      min="0"
                      value={comparePrice}
                      onChange={(e) => setComparePrice(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="0.00"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="flex items-center gap-3 pt-8">
                    <input
                      id="madeToOrder"
                      type="checkbox"
                      checked={madeToOrder}
                      onChange={(e) => setMadeToOrder(e.target.checked)}
                      className="w-4 h-4 text-[#105E53] rounded border-gray-300 focus:ring-[#105E53]"
                    />
                    <label htmlFor="madeToOrder" className="text-sm font-medium text-gray-700">
                      Made to Order
                    </label>
                  </div>

                  <div>
                    <label htmlFor="productionTimeline" className="block text-sm font-medium text-gray-700 mb-2">
                      Estimated Production Time {madeToOrder ? '*' : ''}
                    </label>
                    <input
                      id="productionTimeline"
                      type="text"
                      value={productionTimeline}
                      onChange={(e) => setProductionTimeline(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="E.g., 2-3 weeks"
                      required={madeToOrder}
                    />
                    {madeToOrder && (
                      <p className="mt-2 text-xs text-[#105E53]">
                        Required for made-to-order pieces so customers see the fulfillment timeline.
                      </p>
                    )}
                  </div>
                </div>

                {/* Stock and Status Row */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label htmlFor="stock" className="block text-sm font-medium text-gray-700 mb-2">
                      Total Stock
                    </label>
                    <input
                      id="stock"
                      type="number"
                      min="0"
                      value={stock}
                      onChange={(e) => setStock(e.target.value)}
                      disabled={madeToOrder}
                      className={`w-full rounded-lg border px-4 py-2.5 text-sm transition ${
                        madeToOrder
                          ? 'border-gray-300 bg-gray-100 text-gray-400 cursor-not-allowed'
                          : 'border-gray-300 bg-white focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20'
                      }`}
                      placeholder={madeToOrder ? 'Disabled for made-to-order' : '0'}
                    />
                    <p className="mt-2 text-xs text-gray-500">
                      {madeToOrder
                        ? 'Inventory tracking is disabled for made-to-order products.'
                        : 'Use stock only for ready-to-ship inventory.'}
                    </p>
                  </div>

                  <div>
                    <label htmlFor="status" className="block text-sm font-medium text-gray-700 mb-2">
                      Status
                    </label>
                    <select
                      id="status"
                      value={status}
                      onChange={(e) => setStatus(e.target.value as any)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    >
                      <option value="draft">Draft</option>
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                  {[
                    ['weightKg', 'Weight (kg)', weightKg, setWeightKg],
                    ['lengthCm', 'Length (cm)', lengthCm, setLengthCm],
                    ['widthCm', 'Width (cm)', widthCm, setWidthCm],
                    ['heightCm', 'Height (cm)', heightCm, setHeightCm],
                  ].map(([field, label, value, setter]) => (
                    <div key={field as string}>
                      <label htmlFor={field as string} className="block text-sm font-medium text-gray-700 mb-2">{label as string} *</label>
                      <input
                        id={field as string}
                        type="number"
                        min="0.001"
                        step="0.001"
                        value={value as string}
                        onChange={(e) => (setter as (value: string) => void)(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      />
                    </div>
                  ))}
                </div>

                {/* Info Note */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <p className="text-sm text-blue-800">
                    <strong>Note:</strong> Product images can be deleted and reuploaded before the admin accepts your product. For variations or category changes, please contact support.
                  </p>
                </div>
              </div>
            </div>

            {/* Product Images Card */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mt-6">
              <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Product Images</h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {isApproved
                      ? 'Product approved by administrator. Images are locked.'
                      : 'Designers can edit, delete, and upload images before admin accepts the product.'}
                  </p>
                </div>
                {!isApproved && (
                  <div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/gif"
                      multiple
                      className="hidden"
                      onChange={handleImageUpload}
                      disabled={isUploadingImage || images.length >= 10}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploadingImage || images.length >= 10}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-[#105E53] rounded-lg hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isUploadingImage ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Uploading...
                        </>
                      ) : (
                        <>
                          <Upload className="h-3.5 w-3.5" />
                          Upload Images
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              <div className="p-6">
                {isApproved && (
                  <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3.5 flex items-start gap-2.5">
                    <ShieldAlert className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-800">
                      <strong>Images are locked:</strong> This product has already been approved by the admin. Images cannot be modified after approval. If you need to make changes, please contact support.
                    </p>
                  </div>
                )}

                {images.length > 0 ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                    {images.map((img, index) => (
                      <div
                        key={img.id || index}
                        className="group relative aspect-square rounded-lg overflow-hidden border border-gray-200 bg-gray-50"
                      >
                        <img
                          src={normalizeProductImageUrl(img.thumbnail_url || img.image_url)}
                          alt={`Product ${index + 1}`}
                          className="w-full h-full object-cover"
                        />
                        {img.is_primary && (
                          <span className="absolute top-2 left-2 px-2 py-0.5 text-[10px] font-semibold bg-[#105E53] text-white rounded">
                            Primary
                          </span>
                        )}
                        {!isApproved && (
                          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                            <button
                              type="button"
                              onClick={() => handleDeleteImage(img.id)}
                              disabled={deletingImageId === img.id}
                              className="p-2 bg-red-600 text-white rounded-full hover:bg-red-700 transition shadow-md disabled:opacity-50"
                              title="Delete image"
                              aria-label="Delete image"
                            >
                              {deletingImageId === img.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="py-8 text-center text-gray-500">
                    <ImageIcon className="h-10 w-10 mx-auto text-gray-300 mb-2" />
                    <p className="text-sm">No images uploaded for this product.</p>
                    {!isApproved && (
                      <p className="text-xs text-gray-400 mt-1">
                        Click "Upload Images" above to add product pictures.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                disabled={saving}
                className="px-5 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-[#105E53] rounded-lg hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Changes
                  </>
                )}
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
