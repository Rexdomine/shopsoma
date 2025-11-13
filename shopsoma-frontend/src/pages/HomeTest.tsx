/**
 * Test Home Page - No API calls
 */
import Layout from '../components/layout/Layout';

export default function HomeTest() {
  return (
    <Layout>
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Shopsoma Homepage Test
          </h1>
          <p className="text-lg text-gray-600">
            If you can see this, the basic routing and layout are working!
          </p>
        </div>
      </div>
    </Layout>
  );
}
