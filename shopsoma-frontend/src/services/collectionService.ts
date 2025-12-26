import api from './api';
import type {
  Collection,
  CollectionCreate,
  CollectionDetail,
  CollectionSummary,
  CollectionProductsResponse,
} from '../types';

/**
 * Collection Service
 * Handles all collection-related API calls
 */
export const collectionService = {
  /**
   * Get all collections for the current vendor
   */
  getCollections: async (includeInactive: boolean = true): Promise<CollectionSummary[]> => {
    const response = await api.get('/collections', {
      params: { include_inactive: includeInactive },
    });
    return response.data;
  },

  /**
   * Create a new collection
   */
  createCollection: async (data: CollectionCreate): Promise<Collection> => {
    const response = await api.post('/collections', data);
    return response.data;
  },

  /**
   * Get a single collection by ID
   */
  getCollection: async (collectionId: string): Promise<CollectionDetail> => {
    const response = await api.get(`/collections/${collectionId}`);
    return response.data;
  },

  /**
   * Update a collection
   */
  updateCollection: async (
    collectionId: string,
    data: Partial<CollectionCreate & { is_active: boolean; banner_image_url?: string }>
  ): Promise<Collection> => {
    const response = await api.patch(`/collections/${collectionId}`, data);
    return response.data;
  },

  /**
   * Delete a collection
   */
  deleteCollection: async (collectionId: string): Promise<void> => {
    await api.delete(`/collections/${collectionId}`);
  },

  getCollectionProducts: async (
    collectionId: string,
    params?: { page?: number; page_size?: number; search?: string }
  ): Promise<CollectionProductsResponse> => {
    const response = await api.get(`/collections/${collectionId}/products`, { params });
    return response.data;
  },

  getAvailableCollectionProducts: async (
    collectionId: string,
    params?: { page?: number; page_size?: number; search?: string }
  ): Promise<CollectionProductsResponse> => {
    const response = await api.get(`/collections/${collectionId}/available-products`, { params });
    return response.data;
  },

  addProductsToCollection: async (
    collectionId: string,
    productIds: string[]
  ): Promise<{ updated_count: number }> => {
    const response = await api.post(`/collections/${collectionId}/products`, {
      product_ids: productIds,
    });
    return response.data;
  },

  removeProductFromCollection: async (
    collectionId: string,
    productId: string
  ): Promise<{ removed: boolean }> => {
    const response = await api.delete(`/collections/${collectionId}/products/${productId}`);
    return response.data;
  },
};
