import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminVendorBrandControls, { type BrandControlsVendor } from './AdminVendorBrandControls';
import { adminService } from '../../services/adminService';

vi.mock('../../services/adminService', () => ({
  adminService: {
    updateVendorBrandName: vi.fn(),
    uploadVendorStorefrontImage: vi.fn(),
    removeVendorStorefrontImage: vi.fn(),
  },
}));

const baseVendor: BrandControlsVendor = {
  id: 'vendor-1',
  business_name: 'GLORIA',
  featured_storefront_image_url: 'https://cdn.example.com/banner.jpg',
  is_featured_storefront: false,
};

const setup = (vendor: BrandControlsVendor = baseVendor) => {
  const onUpdated = vi.fn();
  const onMessage = vi.fn();
  render(<AdminVendorBrandControls vendor={vendor} onUpdated={onUpdated} onMessage={onMessage} />);
  return { onUpdated, onMessage };
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AdminVendorBrandControls', () => {
  it('renames the brand with normalised whitespace', async () => {
    vi.mocked(adminService.updateVendorBrandName).mockResolvedValue({ business_name: 'Nouvelle Gloria' });
    const { onUpdated, onMessage } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Edit brand name' }));
    fireEvent.change(screen.getByLabelText('Brand name'), { target: { value: '  Nouvelle   Gloria ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(adminService.updateVendorBrandName).toHaveBeenCalledWith('vendor-1', 'Nouvelle Gloria'));
    expect(onUpdated).toHaveBeenCalledWith({ business_name: 'Nouvelle Gloria' });
    expect(onMessage).toHaveBeenCalledWith('success', expect.stringContaining('Nouvelle Gloria'));
  });

  it('blocks names shorter than two characters without calling the API', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Edit brand name' }));
    fireEvent.change(screen.getByLabelText('Brand name'), { target: { value: ' a ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByRole('alert')).toHaveTextContent('between 2 and 255');
    expect(adminService.updateVendorBrandName).not.toHaveBeenCalled();
  });

  it('uploads a replacement storefront banner', async () => {
    vi.mocked(adminService.uploadVendorStorefrontImage).mockResolvedValue({ featured_storefront_image_url: 'https://cdn.example.com/new.jpg' });
    const { onUpdated } = setup();
    const file = new File(['img'], 'banner.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByLabelText('Choose storefront banner image'), { target: { files: [file] } });
    await waitFor(() => expect(adminService.uploadVendorStorefrontImage).toHaveBeenCalledWith('vendor-1', file));
    expect(onUpdated).toHaveBeenCalledWith({ featured_storefront_image_url: 'https://cdn.example.com/new.jpg' });
  });

  it('rejects non-image files', () => {
    const { onMessage } = setup();
    const file = new File(['x'], 'notes.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('Choose storefront banner image'), { target: { files: [file] } });
    expect(adminService.uploadVendorStorefrontImage).not.toHaveBeenCalled();
    expect(onMessage).toHaveBeenCalledWith('error', expect.stringContaining('image file'));
  });

  it('disables removing the banner of a featured vendor', () => {
    setup({ ...baseVendor, is_featured_storefront: true });
    expect(screen.getByRole('button', { name: /Remove/ })).toBeDisabled();
    expect(screen.getByText(/can be replaced but not removed/)).toBeInTheDocument();
  });

  it('removes the banner after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(adminService.removeVendorStorefrontImage).mockResolvedValue({ featured_storefront_image_url: null });
    const { onUpdated } = setup();
    fireEvent.click(screen.getByRole('button', { name: /Remove/ }));
    await waitFor(() => expect(adminService.removeVendorStorefrontImage).toHaveBeenCalledWith('vendor-1'));
    expect(onUpdated).toHaveBeenCalledWith({ featured_storefront_image_url: null });
  });

  it('links to the public storefront', () => {
    setup();
    expect(screen.getByRole('link', { name: /View storefront/ })).toHaveAttribute('href', '/designers/vendor-1');
  });
});
