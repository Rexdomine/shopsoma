import { useRef, useState, type ChangeEvent } from 'react';
import { ExternalLink, ImageIcon, Pencil, Trash2, Upload } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { DesignerBannerMedia } from '../../pages/designers/DesignerVisuals';

export type BrandControlsVendor = {
  id: string;
  business_name: string;
  featured_storefront_image_url?: string | null;
  is_featured_storefront?: boolean;
};

type Props = {
  vendor: BrandControlsVendor;
  onUpdated: (changes: Partial<BrandControlsVendor>) => void;
  onMessage: (type: 'success' | 'error', text: string) => void;
};

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

const errorDetail = (error: unknown, fallback: string): string => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) return first.msg.replace(/^Value error, /, '');
  }
  return fallback;
};

/**
 * Admin controls for the public designer identity: brand name and the
 * storefront banner shown on /designers and /designers/:id.
 */
export default function AdminVendorBrandControls({ vendor, onUpdated, onMessage }: Props) {
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState(vendor.business_name);
  const [nameError, setNameError] = useState<string | null>(null);
  const [savingName, setSavingName] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const imageUrl = vendor.featured_storefront_image_url || null;

  const startEditing = () => {
    setNameInput(vendor.business_name);
    setNameError(null);
    setEditingName(true);
  };

  const saveName = async () => {
    const trimmed = nameInput.split(/\s+/).filter(Boolean).join(' ');
    if (trimmed.length < 2 || trimmed.length > 255) {
      setNameError('Brand name must be between 2 and 255 characters.');
      return;
    }
    if (trimmed === vendor.business_name) {
      setEditingName(false);
      return;
    }
    setSavingName(true);
    setNameError(null);
    try {
      const result = await adminService.updateVendorBrandName(vendor.id, trimmed);
      onUpdated({ business_name: result.business_name });
      setEditingName(false);
      onMessage('success', `Brand name updated to “${result.business_name}”.`);
    } catch (error) {
      setNameError(errorDetail(error, 'Failed to update brand name.'));
    } finally {
      setSavingName(false);
    }
  };

  const handleImageSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      onMessage('error', 'Please choose an image file (JPG, PNG or WebP).');
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      onMessage('error', 'Image is too large. Please use an image under 10 MB.');
      return;
    }
    setUploading(true);
    try {
      const result = await adminService.uploadVendorStorefrontImage(vendor.id, file);
      setImageFailed(false);
      onUpdated({ featured_storefront_image_url: result.featured_storefront_image_url });
      onMessage('success', 'Storefront banner updated.');
    } catch (error) {
      onMessage('error', errorDetail(error, 'Failed to upload storefront banner.'));
    } finally {
      setUploading(false);
    }
  };

  const removeImage = async () => {
    if (!imageUrl || vendor.is_featured_storefront) return;
    if (!window.confirm(`Remove the storefront banner for ${vendor.business_name}? The storefront will fall back to its first product photo or logo.`)) return;
    setRemoving(true);
    try {
      await adminService.removeVendorStorefrontImage(vendor.id);
      onUpdated({ featured_storefront_image_url: null });
      onMessage('success', 'Storefront banner removed.');
    } catch (error) {
      onMessage('error', errorDetail(error, 'Failed to remove storefront banner.'));
    } finally {
      setRemoving(false);
    }
  };

  return (
    <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6" aria-labelledby="storefront-brand-heading">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <h2 id="storefront-brand-heading" className="text-xl font-display text-gray-900">Storefront &amp; Brand</h2>
          <p className="text-sm text-gray-500 mt-1">
            Controls how this designer appears on the Designers page, their storefront and product pages.
          </p>
        </div>
        <a
          href={`/designers/${encodeURIComponent(vendor.id)}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-[#105E53] hover:underline"
        >
          View storefront <ExternalLink className="w-4 h-4" aria-hidden="true" />
        </a>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-6">
        {/* Brand name */}
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Brand Name</p>
          {editingName ? (
            <div className="space-y-2">
              <label htmlFor="admin-brand-name" className="sr-only">Brand name</label>
              <input
                id="admin-brand-name"
                type="text"
                value={nameInput}
                maxLength={255}
                autoFocus
                disabled={savingName}
                onChange={(event) => setNameInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') { event.preventDefault(); void saveName(); }
                  if (event.key === 'Escape') setEditingName(false);
                }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-[#105E53]"
                aria-invalid={Boolean(nameError)}
                aria-describedby={nameError ? 'admin-brand-name-error' : 'admin-brand-name-help'}
              />
              {nameError ? (
                <p id="admin-brand-name-error" role="alert" className="text-xs text-red-600">{nameError}</p>
              ) : (
                <p id="admin-brand-name-help" className="text-xs text-gray-500">
                  Updates the name everywhere shoppers see it. The designer can also change it from their Brand Info settings.
                </p>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void saveName()}
                  disabled={savingName}
                  className="px-4 py-2 bg-[#105E53] text-white text-xs font-semibold rounded-xl hover:bg-[#0d4a41] disabled:opacity-50 transition"
                >
                  {savingName ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  onClick={() => setEditingName(false)}
                  disabled={savingName}
                  className="px-4 py-2 border border-gray-200 text-gray-700 text-xs font-semibold rounded-xl hover:bg-gray-100 disabled:opacity-50 transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <p className="text-lg font-medium text-gray-900 break-words">{vendor.business_name}</p>
              <button
                type="button"
                onClick={startEditing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 rounded-lg text-xs font-semibold text-gray-700 hover:border-[#105E53] hover:text-[#105E53] transition"
                aria-label="Edit brand name"
              >
                <Pencil className="w-3.5 h-3.5" aria-hidden="true" /> Edit
              </button>
            </div>
          )}
        </div>

        {/* Storefront banner */}
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Storefront Banner</p>
          <div className="designer-banner relative w-full aspect-[16/5] rounded-xl overflow-hidden bg-[#105E53]/10 border border-gray-200">
            {imageUrl && !imageFailed ? (
              <DesignerBannerMedia
                src={imageUrl}
                alt={`Current storefront banner for ${vendor.business_name}`}
                onError={() => setImageFailed(true)}
              />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4 text-[#105E53]">
                <ImageIcon className="w-6 h-6 mb-1" aria-hidden="true" />
                <p className="text-xs">
                  {imageFailed ? 'The current banner could not be loaded.' : 'No banner set — the storefront uses the first product photo or logo.'}
                </p>
              </div>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-2">
            The whole photo is always shown, never cropped. Wide landscape photos fill the banner best; others sit on the right and fade into a soft blurred reflection of the photo.
          </p>
          <div className="flex flex-wrap gap-2 mt-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleImageSelected}
              aria-label="Choose storefront banner image"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || removing}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#105E53] text-white text-xs font-semibold rounded-xl hover:bg-[#0d4a41] disabled:opacity-50 transition"
            >
              <Upload className="w-3.5 h-3.5" aria-hidden="true" />
              {uploading ? 'Uploading…' : imageUrl ? 'Replace banner' : 'Upload banner'}
            </button>
            {imageUrl && (
              <button
                type="button"
                onClick={() => void removeImage()}
                disabled={uploading || removing || Boolean(vendor.is_featured_storefront)}
                title={vendor.is_featured_storefront ? 'Remove this vendor from the featured rotation before removing its banner' : undefined}
                className="inline-flex items-center gap-1.5 px-4 py-2 border border-gray-200 text-gray-700 text-xs font-semibold rounded-xl hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                {removing ? 'Removing…' : 'Remove'}
              </button>
            )}
          </div>
          {imageUrl && vendor.is_featured_storefront && (
            <p className="text-xs text-amber-700 mt-2">This vendor is in the featured rotation, so the banner can be replaced but not removed.</p>
          )}
        </div>
      </div>
    </section>
  );
}
