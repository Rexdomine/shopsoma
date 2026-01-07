import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { info, error as showError } from '../utils/toast';
import Layout from '../components/layout/Layout';
import HeroCarousel from '../components/home/HeroCarousel';
import ProductCard from '../components/products/ProductCard';
import VendorShowcaseCard from '../components/products/VendorShowcaseCard';
import { useWishlistActions } from '../hooks/useWishlistActions';
import { productService } from '../services/productService';
import { designerService } from '../services/designerService';
import type { Product, Vendor } from '../types';
import FeaturedProductSection from '../components/home/FeaturedProductSection';
import Loading from '../components/common/Loading';

const HERO_IMAGES = [
  {
    image: '/images/hero/demo-image-1.png',
    designer: 'Orange Culture',
    title: 'A night Beyond',
    link: '/products/men',
  },
  {
    image: '/images/hero/demo-image-2.png',
    designer: 'Kiko Kostadinov',
    title: 'Modern Tailoring',
    link: '/products/women',
  },
  {
    image: '/images/hero/demo-image-3.png',
    designer: 'Telfar',
    title: 'Effortless Essentials',
    link: '/products/bags-wallets',
  },
];

const CATEGORY_IMAGES = [
  {
    image: '/images/home/man-dress.png',
    name: 'Mens',
    link: '/products/men',
  },
  {
    image: '/images/home/woman-dress.png',
    name: 'Womens',
    link: '/products/women',
  },
  {
    image: '/images/home/bag.png',
    name: 'Bags and Wallets',
    link: '/products/bags-wallets',
  },
  {
    image: '/images/home/perfume.png',
    name: 'Perfumes',
    link: '/products/perfumes',
  },
];

const FEATURED_VENDORS: Vendor[] = [
  {
    id: '1',
    business_name: 'Shopsoma Fashion Store',
    business_description: 'Curated African luxury brands',
    logo_url: '/images/hero/demo-image-2.png',
    status: 'approved',
  },
];

export default function Home() {
  const [featuredProducts, setFeaturedProducts] = useState<Product[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [isLoadingProducts, setIsLoadingProducts] = useState(true);
  const [isLoadingFeatured, setIsLoadingFeatured] = useState(true);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [isLoadingVendors, setIsLoadingVendors] = useState(true);
  const { favorites, toggleFavorite } = useWishlistActions();

  useEffect(() => {
    const fetchProducts = async () => {
      try {
        const response = await productService.getProducts({
          page_size: 8,
          sort_by: 'created_at',
          sort_order: 'desc'
        });
        setProducts(response.products || []);
      } catch (err) {
        console.error('Error fetching products:', err);
        showError('Unable to load latest products');
      } finally {
        setIsLoadingProducts(false);
      }
    };

    const fetchFeaturedProducts = async () => {
      try {
        const response = await productService.getProducts({
          is_featured: true,
          page_size: 12,
          sort_by: 'created_at',
          sort_order: 'desc'
        });
        setFeaturedProducts(response.products || []);
      } catch (err) {
        console.error('Error fetching featured products:', err);
        showError('Unable to load featured products');
      } finally {
        setIsLoadingFeatured(false);
      }
    };

    const fetchVendors = async () => {
      try {
        const response = await designerService.getDesigners();
        setVendors(response || []);
      } catch (err) {
        console.error('Error fetching vendors:', err);
        setVendors(FEATURED_VENDORS);
      } finally {
        setIsLoadingVendors(false);
      }
    };

    fetchProducts();
    fetchFeaturedProducts();
    fetchVendors();
  }, []);

  const featuredVendor = useMemo(() => vendors[0], [vendors]);
  const visibleProducts = useMemo(() => products.slice(0, 6), [products]);

  return (
    <Layout>
      {/* Hero Section */}
      <HeroCarousel slides={HERO_IMAGES} />

      {/* Featured Product Section */}
      <section>
        {isLoadingFeatured ? (
          <div className="py-20">
            <Loading fullScreen={false} message="Loading featured products..." />
          </div>
        ) : (
          <FeaturedProductSection products={featuredProducts} />
        )}
      </section>

      {/* Latest Products Section */}
      <section className="py-12 px-4 max-w-7xl mx-auto">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6">
          <div>
            <h2 className="text-xl font-serif">Shop by Category</h2>
            <p className="text-sm text-gray-600">Explore our curated selection</p>
          </div>
          <Link to="/products" className="mt-4 sm:mt-0 text-sm uppercase tracking-wider border-b border-black">View all</Link>
        </div>

        {isLoadingProducts ? (
          <div className="py-16">
            <Loading fullScreen={false} message="Loading latest products..." />
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {CATEGORY_IMAGES.map((category) => (
              <Link key={category.name} to={category.link} className="flex flex-col gap-2">
                <img src={category.image} alt={category.name} className="rounded-lg object-cover" />
                <span className="text-sm uppercase tracking-widest">{category.name}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Latest Products Grid */}
      <section className="py-8 px-4 max-w-7xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {isLoadingProducts ? (
            <div className="col-span-full py-12">
              <Loading fullScreen={false} message="Loading latest drops..." />
            </div>
          ) : (
            visibleProducts.map(product => (
              <ProductCard
                key={product.id}
                product={product}
                isFavorite={favorites.has(product.id)}
                onToggleFavorite={toggleFavorite}
              />
            ))
          )}
        </div>
      </section>

      {/* Featured Vendor Section */}
      <section className="py-12 px-4 max-w-7xl mx-auto">
        <h2 className="text-xl font-serif mb-4">Featured Vendor</h2>
        {isLoadingVendors ? (
          <div className="py-10">
            <Loading fullScreen={false} message="Loading featured vendor..." />
          </div>
        ) : featuredVendor ? (
          <VendorShowcaseCard
            vendorId={featuredVendor.id}
            vendorName={featuredVendor.business_name}
            imageUrl={featuredVendor.logo_url || FEATURED_VENDORS[0].logo_url}
            productCount={24}
          />
        ) : (
          <div className="text-sm text-gray-500">No featured vendor right now.</div>
        )}
      </section>
    </Layout>
  );
}
