import { useEffect, useMemo, useState } from 'react';
import { X, Upload, Download } from 'lucide-react';
import { productService } from '../../services/productService';

type UploadMode = 'single' | 'variable';

interface BulkUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploaded: (createdCount: number, mode: UploadMode) => void;
}

const SINGLE_HEADERS = [
  'title',
  'description',
  'category_slug',
  'currency',
  'base_price',
  'compare_at_price',
  'total_stock',
  'sku',
  'collection_name',
  'made_to_order',
  'made_to_order_timeline',
  'care_instructions',
  'fabric_composition',
  'status',
];

const VARIABLE_HEADERS = [
  'product_title',
  'description',
  'category_slug',
  'currency',
  'base_price',
  'compare_at_price',
  'product_sku',
  'collection_name',
  'made_to_order',
  'made_to_order_timeline',
  'care_instructions',
  'fabric_composition',
  'color_name',
  'color_hex',
  'size',
  'stock',
  'variant_sku',
  'variation_price',
  'variation_sale_price',
];

const SIZE_VALUES = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'];

const SINGLE_SAMPLE_ROWS = [
  {
    title: 'Classic Linen Shirt',
    description: 'Lightweight linen shirt',
    category_slug: 'menswear-shirts',
    currency: 'NGN',
    base_price: '15000',
    compare_at_price: '18000',
    total_stock: '12',
    sku: 'LINEN-SHIRT-01',
    collection_name: '',
    made_to_order: 'false',
    made_to_order_timeline: '',
    care_instructions: 'Hand wash only',
    fabric_composition: '100% linen',
    status: 'draft',
  },
];

const VARIABLE_SAMPLE_ROWS = [
  {
    product_title: 'Silk Slip Dress',
    description: 'Soft silk slip dress',
    category_slug: 'womens-dresses',
    currency: 'USD',
    base_price: '180',
    compare_at_price: '220',
    product_sku: 'SLIP-DRESS-01',
    collection_name: '',
    made_to_order: 'false',
    made_to_order_timeline: '',
    care_instructions: 'Dry clean only',
    fabric_composition: '100% silk',
    color_name: 'Emerald',
    color_hex: '#0B6E4F',
    size: 'S',
    stock: '4',
    variant_sku: 'SLIP-DRESS-01-EMR-S',
    variation_price: '',
    variation_sale_price: '',
  },
  {
    product_title: 'Silk Slip Dress',
    description: 'Soft silk slip dress',
    category_slug: 'womens-dresses',
    currency: 'USD',
    base_price: '180',
    compare_at_price: '220',
    product_sku: 'SLIP-DRESS-01',
    collection_name: '',
    made_to_order: 'false',
    made_to_order_timeline: '',
    care_instructions: 'Dry clean only',
    fabric_composition: '100% silk',
    color_name: 'Emerald',
    color_hex: '#0B6E4F',
    size: 'M',
    stock: '3',
    variant_sku: 'SLIP-DRESS-01-EMR-M',
    variation_price: '',
    variation_sale_price: '',
  },
];

function toCsv(headers: string[], rows: Record<string, string>[]) {
  const escapeCell = (value: string) => {
    if (value.includes(',') || value.includes('"') || value.includes('\n')) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };
  const lines = [headers.join(',')];
  rows.forEach((row) => {
    const line = headers.map((header) => escapeCell(String(row[header] ?? ''))).join(',');
    lines.push(line);
  });
  return lines.join('\n');
}

function downloadCsvFile(name: string, content: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export default function BulkUploadModal({ isOpen, onClose, onUploaded }: BulkUploadModalProps) {
  const [mode, setMode] = useState<UploadMode>('single');
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [rowErrors, setRowErrors] = useState<Array<{ row: number; field?: string; message: string }>>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [headerErrors, setHeaderErrors] = useState<string[]>([]);

  const requiredHeaders = useMemo(
    () => (mode === 'single' ? SINGLE_HEADERS : VARIABLE_HEADERS),
    [mode]
  );

  useEffect(() => {
    if (!isOpen) {
      setMode('single');
      setFile(null);
      setErrors([]);
      setRowErrors([]);
      setHeaderErrors([]);
    }
  }, [isOpen]);

  useEffect(() => {
    if (file) {
      validateHeaders(file);
    }
  }, [mode]);

  const validateHeaders = async (selectedFile: File) => {
    try {
      const text = await selectedFile.text();
      const [headerLine] = text.split(/\r?\n/);
      if (!headerLine) {
        setHeaderErrors(['CSV file is empty.']);
        return;
      }
      const headers = headerLine.split(',').map((h) => h.trim());
      const missing = requiredHeaders.filter((header) => !headers.includes(header));
      if (missing.length) {
        setHeaderErrors([`Missing headers: ${missing.join(', ')}`]);
        return;
      }
      setHeaderErrors([]);
    } catch (err) {
      setHeaderErrors(['Unable to read the CSV file.']);
    }
  };

  const handleFileChange = async (nextFile: File | null) => {
    setFile(nextFile);
    setErrors([]);
    setRowErrors([]);
    setHeaderErrors([]);
    if (nextFile) {
      await validateHeaders(nextFile);
    }
  };

  const handleDownloadSample = () => {
    if (mode === 'single') {
      const csv = toCsv(SINGLE_HEADERS, SINGLE_SAMPLE_ROWS);
      downloadCsvFile('shopsoma-single-products-sample.csv', csv);
    } else {
      const csv = toCsv(VARIABLE_HEADERS, VARIABLE_SAMPLE_ROWS);
      downloadCsvFile('shopsoma-variable-products-sample.csv', csv);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setErrors(['Please select a CSV file to upload.']);
      return;
    }
    if (headerErrors.length) {
      setErrors(['Fix the CSV header issues before uploading.']);
      return;
    }

    setIsUploading(true);
    setErrors([]);
    setRowErrors([]);

    try {
      const response =
        mode === 'single'
          ? await productService.bulkUploadSingleProducts(file)
          : await productService.bulkUploadVariableProducts(file);

      onUploaded(response.created_count, mode);
      onClose();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (detail?.errors) {
        setRowErrors(detail.errors);
        setErrors([detail.message || 'Validation failed.']);
      } else if (typeof detail === 'string') {
        setErrors([detail]);
      } else {
        setErrors(['Upload failed. Please check your CSV and try again.']);
      }
    } finally {
      setIsUploading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl bg-white rounded-2xl shadow-2xl p-6 m-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-gray-900">Bulk Upload Products</h2>
            <p className="text-sm text-gray-500 mt-1">
              Upload a CSV file to add multiple products at once.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            disabled={isUploading}
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        <div className="flex items-center gap-2 mt-6">
          <button
            type="button"
            onClick={() => setMode('single')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              mode === 'single'
                ? 'bg-[#105E53] text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Single Products CSV
          </button>
          <button
            type="button"
            onClick={() => setMode('variable')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              mode === 'variable'
                ? 'bg-[#105E53] text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Variant Products CSV
          </button>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 p-4 bg-gray-50">
              <h3 className="text-sm font-semibold text-gray-900 mb-2">CSV Instructions</h3>
              {mode === 'single' ? (
                <ul className="text-xs text-gray-600 space-y-1 list-disc list-inside">
                  <li>Use category slug (example: menswear-shirts).</li>
                  <li>Currency must be NGN or USD.</li>
                  <li>Status can be draft, active, inactive, archived.</li>
                  <li>Leave optional fields blank if not needed.</li>
                </ul>
              ) : (
                <ul className="text-xs text-gray-600 space-y-1 list-disc list-inside">
                  <li>Each row represents a single size for a color.</li>
                  <li>Rows with same product_title + category_slug + currency group into one product.</li>
                  <li>Use Size values: {SIZE_VALUES.join(', ')}.</li>
                  <li>variation_price is optional; leave blank to use base_price.</li>
                </ul>
              )}
              <button
                type="button"
                onClick={handleDownloadSample}
                className="mt-3 inline-flex items-center gap-2 text-xs font-medium text-[#105E53] hover:text-[#0c4c45] transition"
              >
                <Download className="h-4 w-4" />
                Download Sample CSV
              </button>
            </div>

            <div className="rounded-xl border border-gray-200 p-4">
              <label className="text-sm font-medium text-gray-700">Upload CSV File</label>
              <div className="mt-2 flex items-center gap-3">
                <label className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 cursor-pointer hover:bg-gray-50 transition">
                  <Upload className="h-4 w-4" />
                  Choose file
                  <input
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={(e) => handleFileChange(e.target.files?.[0] || null)}
                    disabled={isUploading}
                  />
                </label>
                <span className="text-xs text-gray-500">
                  {file ? file.name : 'No file selected'}
                </span>
              </div>
              {headerErrors.length > 0 && (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
                  {headerErrors.map((err, index) => (
                    <p key={`${err}-${index}`}>{err}</p>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-4">
            {(errors.length > 0 || rowErrors.length > 0) && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                <h4 className="text-sm font-semibold text-red-700">Upload Issues</h4>
                {errors.map((err, index) => (
                  <p key={`${err}-${index}`} className="text-xs text-red-600 mt-1">
                    {err}
                  </p>
                ))}
                {rowErrors.length > 0 && (
                  <div className="mt-2 max-h-48 overflow-auto">
                    {rowErrors.map((err, index) => (
                      <p key={`${err.row}-${index}`} className="text-xs text-red-600 mt-1">
                        Row {err.row}: {err.field ? `${err.field} - ` : ''}{err.message}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="rounded-xl border border-gray-200 p-4 bg-gray-50">
              <h4 className="text-sm font-semibold text-gray-900">Before Uploading</h4>
              <ul className="text-xs text-gray-600 space-y-1 list-disc list-inside mt-2">
                <li>Ensure category_slug matches an existing category.</li>
                <li>Collection name is optional; leave blank if not used.</li>
                <li>Upload only CSV files created in UTF-8.</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
            disabled={isUploading}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={isUploading || !file}
            className="px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-[#105E53] hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isUploading ? (
              <>
                <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Uploading...
              </>
            ) : (
              'Upload Products'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
