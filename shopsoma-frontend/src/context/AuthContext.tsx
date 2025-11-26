import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authService, type LoginCredentials, type RegisterData } from '../services/authService';
import type { User } from '../types';
import { STORAGE_KEYS } from '../config/constants';
import { usePreferenceStore } from '../store/preferenceStore';
import { useCartStore } from '../store/cartStore';
import { CartService } from '../services/cartService';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (user: User) => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load user from storage and validate session
  const loadUser = useCallback(async () => {
    console.log('LOAD_USER: Starting loadUser...');
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    console.log('LOAD_USER: Token exists?', !!token);

    if (!token) {
      console.log('LOAD_USER: No token found, setting loading to false');
      setIsLoading(false);
      return;
    }

    try {
      console.log('LOAD_USER: Fetching current user from API...');
      const userData = await authService.getCurrentUser();
      console.log('LOAD_USER: User data received, setting user state');
      setUser(userData);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userData));
      try {
        await useCartStore.getState().syncWithServer();
      } catch (cartError) {
        console.error('LOAD_USER: Failed to sync cart with server', cartError);
      }
    } catch (error) {
      console.log('LOAD_USER: Error fetching user, clearing tokens');
      // Token is invalid, clear it
      localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.USER);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    if (user) {
      useCartStore
        .getState()
        .syncWithServer()
        .catch((error) => console.error('AuthProvider: cart sync failed', error));
    }
  }, [user]);

  const login = useCallback(async (credentials: LoginCredentials) => {
    setIsLoading(true);
    try {
      await authService.login(credentials);
      await loadUser();
    } finally {
      setIsLoading(false);
    }
  }, [loadUser]);

  const register = useCallback(async (data: RegisterData) => {
    setIsLoading(true);
    try {
      await authService.register(data);
      await loadUser();
    } finally {
      setIsLoading(false);
    }
  }, [loadUser]);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      console.log('LOGOUT: Starting logout process...');

      // Clear all localStorage keys (including Zustand persist stores)
      // Get all keys first to avoid iteration issues
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('shopsoma_')) {
          keysToRemove.push(key);
        }
      }
      console.log('LOGOUT: Keys to remove:', keysToRemove);

      // Remove all shopsoma keys
      keysToRemove.forEach(key => {
        console.log('LOGOUT: Removing key:', key);
        localStorage.removeItem(key);
      });
      usePreferenceStore.getState().resetPreferences();
      useCartStore.setState({
        cart: CartService.createEmptyCart(),
        error: null,
        isLoading: false,
      });

      // Verify they're actually gone
      const remainingKeys: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('shopsoma_')) {
          remainingKeys.push(key);
        }
      }
      console.log('LOGOUT: Remaining shopsoma keys after removal:', remainingKeys);

      // Clear user state
      setUser(null);
      console.log('LOGOUT: User state cleared');

      // Make API call to logout (but don't wait for it to finish)
      authService.logout().catch(() => {
        // Ignore errors - we've already cleared local state
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updateUser = useCallback((updatedUser: User) => {
    setUser(updatedUser);
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser));
  }, []);

  const refreshUser = useCallback(async () => {
    await loadUser();
  }, [loadUser]);

  const value = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    register,
    logout,
    updateUser,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
