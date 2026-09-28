import { createServer, type Server } from 'node:http';
import { once } from 'node:events';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import { adminService } from '../adminService';
import { productService } from '../productService';
import { STORAGE_KEYS } from '../../config/constants';

type CapturedRequest = { url: string; contentType: string; authorization?: string; body: Buffer };
const requests: CapturedRequest[] = [];
let server: Server;
const originalBaseURL = api.defaults.baseURL;

beforeAll(async () => {
  // Exercise Axios transforms, interceptors and its browser XHR adapter over HTTP.
  server = createServer(async (request, response) => {
    response.setHeader('Access-Control-Allow-Origin', '*');
    response.setHeader('Access-Control-Allow-Headers', 'authorization, content-type');
    if (request.method === 'OPTIONS') {
      response.writeHead(204).end();
      return;
    }
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    requests.push({
      url: request.url!, contentType: request.headers['content-type'] ?? '',
      authorization: request.headers.authorization, body: Buffer.concat(chunks),
    });
    response.setHeader('Content-Type', 'application/json');
    response.writeHead(201).end(JSON.stringify({ id: 'image-1', image_url: '/uploads/test.png' }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Missing test server address');
  api.defaults.baseURL = `http://127.0.0.1:${address.port}`;
});

afterAll(async () => {
  api.defaults.baseURL = originalBaseURL;
  await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
});

beforeEach(() => {
  requests.length = 0;
  Object.defineProperty(window, 'localStorage', { configurable: true, value: {
    getItem: vi.fn(key => key === STORAGE_KEYS.ACCESS_TOKEN ? 'test-upload-token' : null),
    clear: vi.fn(), setItem: vi.fn(), removeItem: vi.fn(),
  } });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, value: { clear: vi.fn() } });
});

async function expectMultipart(request: CapturedRequest, field: string, names: string[]) {
  expect(request.contentType).toMatch(/^multipart\/form-data; boundary=/);
  expect(request.authorization).toBe('Bearer test-upload-token');
  const boundary = request.contentType.split('boundary=')[1];
  const body = request.body.toString();
  const parts = body.split(`--${boundary}`);
  expect(parts[0]).toBe('');
  expect(parts.at(-1)).toBe('--\r\n');
  expect(parts.slice(1, -1)).toEqual(names.map(name =>
    `\r\nContent-Disposition: form-data; name="${field}"; filename="${name}"\r\nContent-Type: image/png\r\n\r\ntest-image-bytes\r\n`,
  ));
}

const image = (name: string) => new File(['test-image-bytes'], name, { type: 'image/png' });

describe('product upload HTTP serialization', () => {
  it('sends the admin file as multipart bytes with authentication', async () => {
    const result = await adminService.uploadProductImage('product-1', image('front.png'));
    expect(result.id).toBe('image-1');
    expect(requests[0].url).toBe('/admin/products/product-1/images/upload');
    await expectMultipart(requests[0], 'file', ['front.png']);
  });

  it('preserves each file in the sequential admin multiple-upload flow', async () => {
    for (const file of [image('front.png'), image('back.png')]) {
      await adminService.uploadProductImage('product-1', file);
    }
    expect(requests).toHaveLength(2);
    await expectMultipart(requests[0], 'file', ['front.png']);
    await expectMultipart(requests[1], 'file', ['back.png']);
  });

  it('keeps vendor single and batch uploads multipart', async () => {
    await productService.uploadImage(image('front.png'));
    await productService.uploadImages([image('front.png'), image('back.png')]);
    await expectMultipart(requests[0], 'file', ['front.png']);
    await expectMultipart(requests[1], 'files', ['front.png', 'back.png']);
  });

  it('keeps ordinary admin product updates JSON', async () => {
    await adminService.updateProduct('product-1', { title: 'Updated dress' });
    expect(requests[0].contentType).toBe('application/json');
    expect(JSON.parse(requests[0].body.toString())).toEqual({ title: 'Updated dress' });
  });
});
