import { useCartStore } from '../store/cartStore';
import Layout from '../components/layout/Layout';

export default function Debug() {
  const cart = useCartStore((state) => state.cart);
  const addItem = useCartStore((state) => state.addItem);

  const testAddItem = () => {
    try {
      addItem({
        product: {
          id: 'test-123',
          title: 'Test Product',
          base_price: 10000,
          images: [],
          variants: [{
            id: 'var-1',
            size: 'M',
            color: 'Blue',
            price: 10000,
            stock: 10
          }]
        } as any,
        variant: {
          id: 'var-1',
          size: 'M',
          color: 'Blue',
          price: 10000,
          stock: 10
        } as any,
        quantity: 1
      });
      alert('Item added successfully!');
    } catch (error) {
      alert('Error: ' + (error as Error).message);
    }
  };

  return (
    <Layout>
      <div className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-6">Cart Debug Page</h1>

        <div className="space-y-6">
          <div className="border p-4 rounded">
            <h2 className="font-semibold mb-2">Cart Store Status</h2>
            <pre className="bg-gray-100 p-4 rounded text-sm overflow-auto">
              {JSON.stringify(cart, null, 2)}
            </pre>
          </div>

          <div className="border p-4 rounded">
            <h2 className="font-semibold mb-2">Test Actions</h2>
            <button
              onClick={testAddItem}
              className="bg-primary text-white px-4 py-2 rounded hover:bg-primary-dark"
            >
              Test Add Item
            </button>
          </div>

          <div className="border p-4 rounded">
            <h2 className="font-semibold mb-2">Environment Info</h2>
            <ul className="space-y-1 text-sm">
              <li>LocalStorage available: {typeof localStorage !== 'undefined' ? 'Yes' : 'No'}</li>
              <li>Cart items count: {cart.items.length}</li>
              <li>Cart total: ₦{cart.summary.total.toLocaleString()}</li>
            </ul>
          </div>
        </div>
      </div>
    </Layout>
  );
}
