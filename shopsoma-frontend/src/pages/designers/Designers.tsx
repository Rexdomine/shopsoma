import { useEffect, useState } from 'react';
import Layout from '../../components/layout/Layout';
import Loading from '../../components/common/Loading';
import { designerService, type Designer } from '../../services/designerService';

export default function Designers() {
  const [designers, setDesigners] = useState<Designer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDesigners = async () => {
      try {
        setLoading(true);
        const data = await designerService.listDesigners();
        setDesigners(data);
        setError(null);
      } catch (err) {
        console.error('Failed to load designers', err);
        setError('We could not load designers right now. Please try again.');
      } finally {
        setLoading(false);
      }
    };

    loadDesigners();
  }, []);

  if (loading) {
    return <Loading fullScreen message="Loading designers..." />;
  }

  return (
    <Layout>
      <section className="max-w-[1200px] mx-auto px-6 py-10">
        <h1 className="text-3xl font-display text-primary mb-2">Designers</h1>
        <p className="text-sm font-serif text-primary mb-8">
          Discover designers shaping the Shopsoma community.
        </p>
        {error ? (
          <p className="text-sm font-ui text-red-600">{error}</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {designers.map((designer) => (
              <div
                key={designer.id}
                className="border border-[#1E5053]/20 rounded-2xl p-4 bg-white/70"
              >
                <div className="aspect-[4/3] rounded-xl bg-gray-100 overflow-hidden mb-4">
                  {designer.logo_url ? (
                    <img
                      src={designer.logo_url}
                      alt={designer.business_name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-xs font-ui text-gray-500">
                      No logo
                    </div>
                  )}
                </div>
                <h2 className="text-lg font-serif text-primary">{designer.business_name}</h2>
                <p className="text-xs font-ui text-primary/80 mt-1">
                  {designer.total_products} products · {designer.total_orders} orders
                </p>
              </div>
            ))}
          </div>
        )}
      </section>
    </Layout>
  );
}
