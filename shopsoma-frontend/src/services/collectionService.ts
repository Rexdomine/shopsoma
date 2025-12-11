import api from './api';
import type { Collection, CollectionCreate } from '../types';

/**
 * Collection Service
 * Handles all collection-related API calls
 */
export const collectionService = {
  /**
   * Get all collections for the current vendor
   */
  getCollections: async (): Promise<Collection[]> => {
    const response = await api.get('/collections');
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
  getCollection: async (collectionId: string): Promise<Collection> => {
    const response = await api.get(`/collections/${collectionId}`);
    return response.data;
  },

  /**
   * Update a collection
   */
  updateCollection: async (
    collectionId: string,
    data: Partial<CollectionCreate>
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
};
