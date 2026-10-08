import { describe, expect, it, vi, beforeEach } from 'vitest';
import api from '../api';
import axios from 'axios';
import { STORAGE_KEYS } from '../../config/constants';

vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios');
  const mockPost = vi.fn();
  return {
    ...actual,
    default: {
      ...actual.default,
      create: actual.default.create,
      post: mockPost,
    },
  };
});

describe('API Interceptor Auth Protections', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('rejects /auth/login errors without triggering token refresh or page reload', async () => {
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, 'dummy-refresh-token');

    // Simulate 401 error on /auth/login
    const error: any = {
      config: { url: '/auth/login' },
      response: { status: 401, data: { detail: 'Incorrect email or password' } },
    };

    // Find the response error interceptor handler
    const responseInterceptor = (api.interceptors.response as any).handlers[0]?.rejected;
    expect(responseInterceptor).toBeDefined();

    await expect(responseInterceptor(error)).rejects.toEqual(error);

    // axios.post should NOT have been called with /auth/refresh
    expect(axios.post).not.toHaveBeenCalled();
    // Refresh token should still exist and not be cleared by login failure
    expect(localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)).toBe('dummy-refresh-token');
  });

  it('does not navigate window.location.href when already on /vendor/login', async () => {
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, 'expired-refresh');

    const originalLocation = window.location;
    const hrefSetter = vi.fn();

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        pathname: '/vendor/login',
        get href() {
          return 'http://localhost:5173/vendor/login';
        },
        set href(val: string) {
          hrefSetter(val);
        },
      },
    });

    const error: any = {
      config: { url: '/vendor/profile' },
      response: { status: 401 },
    };

    (axios.post as any).mockRejectedValueOnce(new Error('Refresh failed'));

    const responseInterceptor = (api.interceptors.response as any).handlers[0]?.rejected;
    await expect(responseInterceptor(error)).rejects.toThrow();

    expect(hrefSetter).not.toHaveBeenCalled();

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });
});
