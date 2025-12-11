import api from './api';
import type { Category } from '../types';

/**
 * Category Service
 * Handles all category-related API calls
 */
export const categoryService = {
  /**
   * Get primary categories (Men, Women, Beauty)
   */
  getPrimaryCategories: async (): Promise<Category[]> => {
    const response = await api.get('/categories');
    return response.data;
  },

  /**
   * Get subcategories of a specific parent category
   */
  getSubcategories: async (parentId: string): Promise<Category[]> => {
    const response = await api.get(`/categories?parent_id=${parentId}`);
    return response.data;
  },

  /**
   * Get all categories in a flat list
   */
  getAllCategories: async (): Promise<Category[]> => {
    const response = await api.get('/categories/all');
    return response.data;
  },

  /**
   * Get a single category by ID
   */
  getCategory: async (categoryId: string): Promise<Category> => {
    const response = await api.get(`/categories/${categoryId}`);
    return response.data;
  },
};
