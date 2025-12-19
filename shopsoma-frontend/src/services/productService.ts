import api from './api';
import type { Product, ImageUploadResponse, ImageBatchUploadResponse } from '../types';

export interface ProductListParams {
  page?: number;
  page_size?: number;
  category_id?: string;
  min_price?: number;
  max_price?: number;
  vendor_id?: string;
  is_featured?: boolean;
  search?: string;
  sort_by?: 'created_at' | 'title' | 'base_price' | 'orders_count' | 'views_count';
  sort_order?: 'asc' | 'desc';
  in_stock?: boolean;
  status?: string;
}

export interface ProductListResponse {
  products: Product[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const productService = {
  // Get all products with filters
  async getProducts(params?: ProductListParams): Promise<ProductListResponse> {
    const response = await api.get('/products', { params });
    return response.data;
  },

  // Get single product by ID
  async getProduct(productId: string): Promise<Product> {
    const response = await api.get(`/products/${productId}`);
    return response.data;
  },

  // Get featured products
  async getFeaturedProducts(pageSize: number = 8): Promise<Product[]> {
    const response = await api.get('/products', {
      params: {
        is_featured: true,
        page_size: pageSize,
        sort_by: 'created_at',
        sort_order: 'desc'
      },
    });
    return response.data.products;
  },

  // Get products by category
  async getProductsByCategory(
    categoryId: string,
    pageSize?: number
  ): Promise<Product[]> {
    const response = await api.get('/products', {
      params: {
        category_id: categoryId,
        page_size: pageSize,
        sort_by: 'created_at',
        sort_order: 'desc'
      },
    });
    return response.data.products;
  },

  // Search products
  async searchProducts(
    query: string,
    params?: ProductListParams
  ): Promise<ProductListResponse> {
    const response = await api.get('/products', {
      params: { search: query, ...params },
    });
    return response.data;
  },

  // Get vendor products
  async getVendorProducts(
    vendorId: string,
    params?: ProductListParams
  ): Promise<ProductListResponse> {
    const response = await api.get('/products', {
      params: { vendor_id: vendorId, ...params },
    });
    return response.data;
  },

  // Create product (vendor only)
  async createProduct(productData: Partial<Product>): Promise<Product> {
    const response = await api.post('/products', productData);
    return response.data;
  },

  // Update product (vendor only)
  async updateProduct(
    productId: string,
    productData: Partial<Product>
  ): Promise<Product> {
    const response = await api.put(`/products/${productId}`, productData);
    return response.data;
  },

  // Delete product (vendor only)
  async deleteProduct(productId: string): Promise<void> {
    await api.delete(`/products/${productId}`);
  },

  // Duplicate product (vendor only)
  async duplicateProduct(productId: string): Promise<Product> {
    // Fetch the original product
    const original = await this.getProduct(productId);

    // Create a copy with modified title and reset certain fields
    const duplicateData: Partial<Product> = {
      title: `${original.title} (Copy)`,
      description: original.description,
      base_price: original.base_price,
      compare_at_price: original.compare_at_price,
      category_id: original.category_id,
      collection_id: original.collection_id,
      status: 'draft' as const,
      is_featured: false,
      // Copy variations if they exist
      variations: original.variations?.map(v => ({
        title: v.title,
        type: v.type,
        color_hex: v.color_hex,
        price: v.price,
        sale_price: v.sale_price,
        images: v.images,
        is_active: v.is_active,
        size_stocks: v.size_stocks.map(ss => ({
          size: ss.size,
          stock: ss.stock,
        })),
      })),
      // Copy images if they exist (remove id and product_id)
      images: original.images?.map(img => ({
        image_url: img.image_url,
        thumbnail_url: img.thumbnail_url,
        alt_text: img.alt_text,
        display_order: img.display_order,
        is_primary: img.is_primary,
      })) as any,
    };

    // Create the duplicate
    const response = await api.post('/products', duplicateData);
    return response.data;
  },

  // Upload single image
  async uploadImage(
    file: File,
    folder: string = 'products',
    generateVariants: boolean = true
  ): Promise<ImageUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/images/upload', formData, {
      params: {
        folder,
        generate_variants: generateVariants,
      },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Upload multiple images
  async uploadImages(
    files: File[],
    folder: string = 'products',
    generateVariants: boolean = true
  ): Promise<ImageBatchUploadResponse> {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const response = await api.post('/images/upload/batch', formData, {
      params: {
        folder,
        generate_variants: generateVariants,
      },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};
