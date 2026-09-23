import { createElement } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BulkUploadModal from '../BulkUploadModal';
import { productService } from '../../../services/productService';

vi.mock('../../../services/productService', () => ({
  productService: {
    bulkUploadSingleProducts: vi.fn(),
    bulkUploadVariableProducts: vi.fn(),
  },
}));

const imageHeaders = Array.from({ length: 5 }, (_, index) => `image_${index + 1}_url`);
let downloadedBlob: Blob;
let downloadedName: string;

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsText(blob);
  });
}

async function downloadSample(mode: 'single' | 'variable') {
  if (mode === 'variable') {
    fireEvent.click(screen.getByRole('button', { name: 'Variant Products CSV' }));
  }
  fireEvent.click(screen.getByRole('button', { name: 'Download Sample CSV' }));
  return readBlob(downloadedBlob);
}

async function chooseFile(text: string) {
  const file = new File([text], 'products.csv', { type: 'text/csv' });
  Object.defineProperty(file, 'text', { value: async () => text });
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  await act(async () => fireEvent.change(input, { target: { files: [file] } }));
  return file;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productService.bulkUploadSingleProducts).mockResolvedValue({ created_count: 1 });
  vi.mocked(productService.bulkUploadVariableProducts).mockResolvedValue({ created_count: 1 });
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL(blob: Blob) {
      downloadedBlob = blob;
      return 'blob:test-download';
    }
    static revokeObjectURL = vi.fn();
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloadedName = this.download;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('bulk product CSV image downloads and uploads', () => {
  it.each(['single', 'variable'] as const)('downloads %s sample with optional image columns and aligned rows', async (mode) => {
    render(createElement(BulkUploadModal, { isOpen: true, onClose: vi.fn(), onUploaded: vi.fn() }));
    const csv = await downloadSample(mode);
    const [headerLine, ...rowLines] = csv.split('\n');
    const headers = headerLine.split(',');
    expect(headers.slice(-5)).toEqual(imageHeaders);
    expect(downloadedName).toBe(`shopsoma-${mode === 'single' ? 'single' : 'variable'}-products-sample.csv`);
    expect(downloadedBlob.type).toContain('text/csv');
    expect(rowLines).toHaveLength(mode === 'single' ? 1 : 2);
    const rows = rowLines.map(line => line.split(','));
    expect(rows.every(row => row.length === headers.length)).toBe(true);
    expect(rows[0][headers.indexOf('image_1_url')]).toMatch(/^https:\/\//);
    expect(rows[0][headers.indexOf('image_2_url')]).toMatch(/^https:\/\//);
    if (mode === 'variable') {
      expect(rows[1].slice(-5)).toEqual(['', '', '', '', '']);
      for (const key of ['product_title', 'category_slug', 'currency', 'product_sku']) {
        expect(rows[1][headers.indexOf(key)]).toEqual(rows[0][headers.indexOf(key)]);
      }
    }
    expect(screen.getByText(/first nonblank URL is the primary image/)).toBeInTheDocument();
    expect(screen.getByText(/Replace sample photographs with your own/)).toBeInTheDocument();
  });

  it.each(['single', 'variable'] as const)('still uploads legacy %s CSV without image columns', async (mode) => {
    const onUploaded = vi.fn();
    render(createElement(BulkUploadModal, { isOpen: true, onClose: vi.fn(), onUploaded }));
    const csv = await downloadSample(mode);
    const legacyCsv = csv.split('\n').map(line => line.split(',').slice(0, -5).join(',')).join('\n');
    const file = await chooseFile(legacyCsv);
    expect(screen.queryByText(/Missing headers:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Upload Products' }));
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(1, mode));
    const service = mode === 'single' ? productService.bulkUploadSingleProducts : productService.bulkUploadVariableProducts;
    expect(service).toHaveBeenCalledWith(file);
  });

  it.each(['single', 'variable'] as const)('uploads the downloaded %s image CSV unchanged', async (mode) => {
    const onUploaded = vi.fn();
    render(createElement(BulkUploadModal, { isOpen: true, onClose: vi.fn(), onUploaded }));
    const csv = await downloadSample(mode);
    const file = await chooseFile(csv);
    fireEvent.click(screen.getByRole('button', { name: 'Upload Products' }));
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(1, mode));
    const service = mode === 'single' ? productService.bulkUploadSingleProducts : productService.bulkUploadVariableProducts;
    expect(service).toHaveBeenCalledWith(file);
    expect(await file.text()).toBe(csv);
  });

  it('validates headers against the selected mode, not the file contents', async () => {
    render(createElement(BulkUploadModal, { isOpen: true, onClose: vi.fn(), onUploaded: vi.fn() }));
    const variableCsv = await downloadSample('variable');
    fireEvent.click(screen.getByRole('button', { name: 'Single Products CSV' }));
    await chooseFile(variableCsv);
    expect(screen.getByText(/Missing headers:.*title.*total_stock/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Upload Products' }));
    expect(productService.bulkUploadSingleProducts).not.toHaveBeenCalled();
  });

  it('shows row-specific backend image validation errors', async () => {
    vi.mocked(productService.bulkUploadSingleProducts).mockRejectedValue({
      response: { data: { detail: { message: 'Validation failed', errors: [
        { row: 2, field: 'image_1_url', message: 'Use a public HTTPS image URL' },
      ] } } },
    });
    render(createElement(BulkUploadModal, { isOpen: true, onClose: vi.fn(), onUploaded: vi.fn() }));
    const csv = await downloadSample('single');
    await chooseFile(csv);
    fireEvent.click(screen.getByRole('button', { name: 'Upload Products' }));
    expect(await screen.findByText(/image_1_url.*Use a public HTTPS image URL/)).toBeInTheDocument();
  });
});
