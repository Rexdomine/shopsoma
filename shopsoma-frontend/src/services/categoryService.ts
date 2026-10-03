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

  /**
   * Get all categories with administrative hierarchy metadata (for admin)
   */
  getAdminCategories: async (): Promise<Category[]> => {
    const response = await api.get('/admin/categories');
    return response.data.categories || [];
  },

  /**
   * Create a new category (Primary, Subcategory, or Child category)
   */
  createCategory: async (data: {
    name: string;
    parent_id?: string | null;
    slug?: string;
    description?: string;
    display_order?: number;
    is_active?: boolean;
  }): Promise<Category> => {
    const response = await api.post('/admin/categories', data);
    return response.data.category;
  },

  /**
   * Update an existing category
   */
  updateCategory: async (
    categoryId: string,
    data: {
      name?: string;
      parent_id?: string | null;
      slug?: string;
      description?: string;
      display_order?: number;
      is_active?: boolean;
    }
  ): Promise<Category> => {
    const response = await api.put(`/admin/categories/${categoryId}`, data);
    return response.data.category;
  },

  /**
   * Delete a category
   */
  deleteCategory: async (categoryId: string): Promise<void> => {
    await api.delete(`/admin/categories/${categoryId}`);
  },
};

