import { beforeEach, expect, it, vi } from 'vitest';
import { productService } from '../productService';
const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('../api', () => ({ default: api }));
beforeEach(() => { vi.clearAllMocks(); });

it('delegates duplication to the server without URL/key payloads or automatic retry', async () => {
  api.post.mockResolvedValue({ data: { id: 'draft' } });
  expect(await productService.duplicateProduct('source')).toEqual({ id: 'draft' });
  expect(api.get).not.toHaveBeenCalled();
  expect(api.post).toHaveBeenCalledWith('/products/source/duplicate', undefined, {
    timeout: 10000, _retry: true,
  });
});

it('propagates a lost acknowledgement without submitting a second request', async () => {
  api.post.mockRejectedValue(new Error('timeout'));
  await expect(productService.duplicateProduct('source')).rejects.toThrow('timeout');
  expect(api.post).toHaveBeenCalledTimes(1);
});
