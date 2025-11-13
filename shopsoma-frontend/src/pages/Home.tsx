/**
 * Home Page
 */
import Layout from '../components/layout/Layout';
import HeroSection from '../components/home/HeroSection';
import ProductRecommendation from '../components/home/ProductRecommendation';
import BestSellers from '../components/home/BestSellers';
import LatestArticles from '../components/home/LatestArticles';
import Newsletter from '../components/home/Newsletter';

export default function Home() {
  return (
    <Layout>
      <HeroSection />
      <ProductRecommendation />
      <BestSellers />
      <LatestArticles />
      <Newsletter />
    </Layout>
  );
}
