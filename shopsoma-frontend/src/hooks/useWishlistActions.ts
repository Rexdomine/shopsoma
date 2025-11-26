import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../config/constants';
import { wishlistService } from '../services/wishlistService';
import { useAuth } from '../context/AuthContext';

export function useWishlistActions() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let isMounted = true;
    if (!isAuthenticated) {
      setFavorites(new Set());
      return () => {
        isMounted = false;
      };
    }

    (async () => {
      try {
        const data = await wishlistService.getWishlist();
        if (isMounted) {
          setFavorites(new Set(data.items.map((item) => item.product_id)));
        }
      } catch (error) {
        console.error('Failed to load wishlist', error);
      }
    })();

    return () => {
      isMounted = false;
    };
  }, [isAuthenticated]);

  const toggleFavorite = useCallback(
    async (productId: string) => {
      if (!isAuthenticated) {
        navigate(ROUTES.LOGIN);
        return;
      }

      setLoadingIds((prev) => {
        const next = new Set(prev);
        next.add(productId);
        return next;
      });

      try {
        if (favorites.has(productId)) {
          await wishlistService.removeFromWishlist(productId);
          setFavorites((prev) => {
            const next = new Set(prev);
            next.delete(productId);
            return next;
          });
        } else {
          await wishlistService.addToWishlist(productId);
          setFavorites((prev) => {
            const next = new Set(prev);
            next.add(productId);
            return next;
          });
        }
      } catch (error) {
        console.error('Failed to update wishlist', error);
      } finally {
        setLoadingIds((prev) => {
          const next = new Set(prev);
          next.delete(productId);
          return next;
        });
      }
    },
    [favorites, isAuthenticated, navigate],
  );

  return {
    favorites,
    toggleFavorite,
    loadingIds,
  };
}
