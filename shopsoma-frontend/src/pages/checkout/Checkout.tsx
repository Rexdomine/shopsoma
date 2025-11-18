import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';

interface ShippingAddress {
  firstName: string;
  lastName: string;
  phone: string;
  country: string;
  address: string;
  postalCode: string;
  city: string;
  useAsBilling: boolean;
}

type Step = 'email' | 'address' | 'shipping' | 'payment';

const mockShippingOptions = [
  { id: 'express', name: 'Express', description: '2 - 4 business days after shipping', price: 51000 },
];

const mockPaymentOptions = [
  { id: 'paystack', name: 'Paystack', icon: '/images/paystack.svg' },
  { id: 'stripe', name: 'Stripe', icon: '/images/stripe.svg' },
];

export default function Checkout() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [address, setAddress] = useState<ShippingAddress>({
    firstName: '',
    lastName: '',
    phone: '',
    country: 'Nigeria',
    address: '',
    postalCode: '',
    city: '',
    useAsBilling: true,
  });
  const [shippingMethod, setShippingMethod] = useState(mockShippingOptions[0].id);
  const [paymentMethod, setPaymentMethod] = useState(mockPaymentOptions[0].id);

  const hasEmail = email.trim().length > 3;
  const hasAddress = address.firstName && address.lastName && address.address && address.city;
  const canPurchase = step === 'payment' && hasEmail && hasAddress;

  const [promo, setPromo] = useState('');
  const [discount, setDiscount] = useState(0);

  const subtotal = 470000;
  const shipping = mockShippingOptions.find((opt) => opt.id === shippingMethod)?.price ?? 0;
  const total = subtotal + shipping - discount;

  const handleApplyPromo = () => {
    if (promo.trim().toLowerCase() === 'save10') {
      setDiscount(Math.round(subtotal * 0.1));
    } else {
      setDiscount(0);
    }
  };

  const goBackToBag = () => navigate(ROUTES.CART);

  const handleEmailConfirm = () => {
    if (hasEmail) setStep('address');
  };

  const handleAddressSave = () => {
    if (hasAddress) setStep('shipping');
  };

  const handleShippingSave = () => {
    setStep('payment');
  };

  const renderStepTitle = (label: string, active: boolean) => (
    <p className={`text-sm font-semibold uppercase tracking-[0.2em] ${active ? 'text-dark' : 'text-gray-300'}`}>
      {label}
    </p>
  );

  return (
    <Layout showHeader={false}>
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 grid grid-cols-3 items-center">
          <button
            onClick={goBackToBag}
            className="text-sm text-primary font-semibold justify-self-start hover:underline"
          >
            ← Back to Shopping Bag
          </button>
          <div className="flex items-center justify-center">
            <Link to="/" className="flex items-center justify-center">
              <img src="/images/somalogo.svg" alt="Shopsoma" className="h-10 w-auto" />
            </Link>
          </div>
          <div className="flex items-center justify-end gap-3 text-sm">
            <span className="text-gray-700">Secure Checkout</span>
            <span className="text-gray-400">
              Need help?{' '}
              <button className="text-primary font-semibold">Contact Us</button>
            </span>
          </div>
        </div>
      </header>
      <section className="bg-white py-8 lg:py-12">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">

          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-10">
            <div className="space-y-6">
              <div className="border-b pb-4">
                <h2 className="text-center text-lg font-semibold uppercase tracking-[0.2em] text-gray-700">Checkout</h2>
              </div>

              <div className="space-y-8">
                <div className="space-y-3">
                  {renderStepTitle('Your Email', true)}
                  <div className="flex items-center gap-4 max-w-2xl">
                    <div className="flex-1">
                      <label className="text-xs text-gray-500">Email</label>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                        placeholder="you@example.com"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleEmailConfirm}
                      disabled={!hasEmail}
                      className="px-6 py-2 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
                    >
                      Confirm
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {renderStepTitle('Addresses', step !== 'email')}
                  {step === 'address' || step === 'shipping' || step === 'payment' ? (
                    <div className="space-y-3 max-w-2xl">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-xs text-gray-500">First Name</label>
                          <input
                            type="text"
                            value={address.firstName}
                            onChange={(e) => setAddress({ ...address, firstName: e.target.value })}
                            className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Last Name</label>
                          <input
                            type="text"
                            value={address.lastName}
                            onChange={(e) => setAddress({ ...address, lastName: e.target.value })}
                            className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">Phone</label>
                        <input
                          type="tel"
                          value={address.phone}
                          onChange={(e) => setAddress({ ...address, phone: e.target.value })}
                          className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">Country</label>
                        <input
                          type="text"
                          value={address.country}
                          onChange={(e) => setAddress({ ...address, country: e.target.value })}
                          className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">Complete Street Address (Number & Name)</label>
                        <input
                          type="text"
                          value={address.address}
                          onChange={(e) => setAddress({ ...address, address: e.target.value })}
                          className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-xs text-gray-500">Postal Code/ Zip</label>
                          <input
                            type="text"
                            value={address.postalCode}
                            onChange={(e) => setAddress({ ...address, postalCode: e.target.value })}
                            className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">City</label>
                          <input
                            type="text"
                            value={address.city}
                            onChange={(e) => setAddress({ ...address, city: e.target.value })}
                            className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                          />
                        </div>
                      </div>
                      <label className="inline-flex items-center gap-2 text-sm text-gray-600">
                        <input
                          type="checkbox"
                          checked={address.useAsBilling}
                          onChange={(e) => setAddress({ ...address, useAsBilling: e.target.checked })}
                          className="h-4 w-4 border-gray-400"
                        />
                        Use as Billing Address
                      </label>
                      <div className="pt-4">
                        <button
                          type="button"
                          onClick={handleAddressSave}
                          disabled={!hasAddress}
                          className="w-full py-3 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-gray-300 text-sm">Addresses</p>
                  )}
                </div>

                <div className="space-y-4">
                  {renderStepTitle('Shipping Method', step === 'shipping' || step === 'payment')}
                  {step === 'shipping' || step === 'payment' ? (
                    <div className="space-y-3">
                      {mockShippingOptions.map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => setShippingMethod(option.id)}
                          className={`w-full text-left border border-gray-200 px-4 py-3 flex items-center gap-4 ${
                            shippingMethod === option.id ? 'bg-gray-50 border-primary' : ''
                          }`}
                        >
                          <div className="w-12 h-12 border border-gray-300 rounded flex items-center justify-center text-gray-500 text-sm">
                            📦
                          </div>
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-gray-800">{option.name}</p>
                            <p className="text-xs text-gray-500">{option.description}</p>
                          </div>
                          <p className="text-sm font-semibold text-gray-800">₦{option.price.toLocaleString()}</p>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={handleShippingSave}
                        className="px-6 py-2 rounded-sm bg-primary text-white text-sm font-semibold"
                      >
                        Continue
                      </button>
                    </div>
                  ) : (
                    <p className="text-gray-300 text-sm">Shipping Method</p>
                  )}
                </div>

                <div className="space-y-4">
                  {renderStepTitle('Payment Method', step === 'payment')}
                  {step === 'payment' ? (
                    <div className="space-y-3">
                      {mockPaymentOptions.map((option) => (
                        <label
                          key={option.id}
                          className={`flex items-center justify-between border border-gray-200 px-4 py-3 cursor-pointer ${
                            paymentMethod === option.id ? 'bg-gray-50 border-primary' : ''
                          }`}
                        >
                          <span className="flex items-center gap-3 text-sm text-gray-800">
                            <input
                              type="radio"
                              name="payment"
                              checked={paymentMethod === option.id}
                              onChange={() => setPaymentMethod(option.id)}
                              className="text-primary"
                            />
                            {option.name}
                          </span>
                          {option.icon && (
                            <img src={option.icon} alt={option.name} className="h-6" />
                          )}
                        </label>
                      ))}
                      <button
                        type="button"
                        className="w-full py-3 rounded-sm bg-primary text-white text-sm font-semibold"
                      >
                        Purchase
                      </button>
                    </div>
                  ) : (
                    <p className="text-gray-300 text-sm">Payment Method</p>
                  )}
                </div>
              </div>
            </div>

            <aside className="border border-gray-200 rounded-sm p-5 space-y-4 sticky top-6 h-fit">
              <div className="flex items-center justify-between text-sm font-semibold text-gray-800">
                <span>Order</span>
              </div>
              <div className="text-sm text-gray-700 space-y-2">
                <div className="flex items-center justify-between">
                  <span>Subtotal</span>
                  <span>₦{subtotal.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Shipping cost</span>
                  <span>₦{shipping.toLocaleString()}</span>
                </div>
                {discount > 0 && (
                  <div className="flex items-center justify-between text-primary">
                    <span>Promo</span>
                    <span>-₦{discount.toLocaleString()}</span>
                  </div>
                )}
                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="text"
                    value={promo}
                    onChange={(e) => setPromo(e.target.value)}
                    placeholder="Promo code"
                    className="flex-1 border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary"
                  />
                  <button
                    type="button"
                    onClick={handleApplyPromo}
                    className="px-4 py-2 rounded-sm bg-primary text-white text-sm font-semibold"
                  >
                    Apply
                  </button>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm font-semibold text-gray-800 border-t border-gray-200 pt-3">
                <span>Total</span>
                <span>₦{total.toLocaleString()}</span>
              </div>
              <button
                className={`w-full py-3 rounded-sm text-sm font-semibold ${
                  canPurchase ? 'bg-primary text-white hover:bg-primary-dark transition' : 'bg-gray-200 text-gray-500'
                }`}
                disabled={!canPurchase}
              >
                Purchase
              </button>
            </aside>
          </div>
        </div>
      </section>
    </Layout>
  );
}
