import { describe, expect, it, vi } from 'vitest';
import api from '../api';
import { adminService } from '../adminService';

vi.mock('../api', () => ({ default: { put: vi.fn() } }));

describe('admin user status service', () => {
  it('bulk updates explicit user ids through the reversible status endpoint', async () => {
    vi.mocked(api.put).mockResolvedValueOnce({ data: { requested_count: 2, updated_count: 2, results: [] } });
    await adminService.bulkUpdateUserStatus(['u1', 'u2'], false);
    expect(api.put).toHaveBeenCalledWith('/admin/users/status/bulk', { user_ids: ['u1', 'u2'], is_active: false });
  });
});
