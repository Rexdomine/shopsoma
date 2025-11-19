import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import { checkoutService, type Address, type ShippingRate, type OrderReview, type CreateAddressData } from '../../services/checkoutService';
import { CartService } from '../../services/cartService';
import { paymentService } from '../../services/paymentService';
import type { Cart } from '../../types/cart';

// Declare Paystack type
declare global {
  interface Window {
    PaystackPop: any;
  }
}

type Step = 'email' | 'address' | 'shipping' | 'payment';

interface NewAddress {
  full_name: string;
  phone_number: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code?: string;
  country: string;
  address_type: 'shipping' | 'billing';
  is_default: boolean;
}

const mockPaymentOptions = [
  { id: 'paystack', name: 'Paystack', icon: '/images/paystack.svg' },
  { id: 'stripe', name: 'Stripe', icon: '/images/stripe.svg' },
];

export default function Checkout() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [isEmailConfirmed, setIsEmailConfirmed] = useState(false);
  const [isEditingEmail, setIsEditingEmail] = useState(false);
  const [isGuestCheckout, setIsGuestCheckout] = useState(false);
  const [cart, setCart] = useState<Cart>(CartService.getCart());

  // Address state
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [selectedAddressId, setSelectedAddressId] = useState<string>('');
  const [showNewAddressForm, setShowNewAddressForm] = useState(false);
  const [newAddress, setNewAddress] = useState<NewAddress>({
    full_name: '',
    phone_number: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: 'Nigeria',
    address_type: 'shipping',
    is_default: false,
  });

  // Shipping state
  const [shippingRates, setShippingRates] = useState<ShippingRate[]>([]);
  const [selectedShippingRateId, setSelectedShippingRateId] = useState<string>('');

  // Promo code state
  const [promo, setPromo] = useState('');
  const [promoError, setPromoError] = useState('');
  const [appliedPromo, setAppliedPromo] = useState<{
    code: string;
    discount_type: 'percentage' | 'fixed_amount';
    discount_value: number;
    discount_amount: number;
  } | null>(null);

  // Order review state
  const [orderReview, setOrderReview] = useState<OrderReview | null>(null);

  // Payment state
  const [paymentMethod, setPaymentMethod] = useState(mockPaymentOptions[0].id);

  // Loading states
  const [isLoadingAddresses, setIsLoadingAddresses] = useState(false);
  const [isLoadingShipping, setIsLoadingShipping] = useState(false);
  const [isApplyingPromo, setIsApplyingPromo] = useState(false);
  const [isCreatingOrder, setIsCreatingOrder] = useState(false);

  // Email validation state
  const [emailError, setEmailError] = useState('');

  // Check authentication and load addresses on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      // User is logged in, load their saved addresses
      loadAddresses();
    } else {
      // User not logged in, enable guest checkout
      setIsGuestCheckout(true);
    }
  }, []);

  const loadAddresses = async () => {
    setIsLoadingAddresses(true);
    try {
      const data = await checkoutService.getAddresses();
      setAddresses(data.addresses);

      // Auto-select default address if exists
      const defaultAddr = data.addresses.find(addr => addr.is_default && addr.address_type === 'shipping');
      if (defaultAddr) {
        setSelectedAddressId(defaultAddr.id);
      }
    } catch (error) {
      console.error('Error loading addresses:', error);
    } finally {
      setIsLoadingAddresses(false);
    }
  };

  const handleCreateAddress = async () => {
    // For guest checkout, just use the address locally without saving to backend
    if (isGuestCheckout) {
      const guestAddress: Address = {
        id: 'guest-address',
        user_id: 'guest',
        full_name: newAddress.full_name,
        phone_number: newAddress.phone_number,
        address_line1: newAddress.address_line1,
        address_line2: newAddress.address_line2,
        city: newAddress.city,
        state: newAddress.state,
        postal_code: newAddress.postal_code,
        country: newAddress.country,
        address_type: newAddress.address_type,
        is_default: newAddress.is_default,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      setAddresses([guestAddress]);
      setSelectedAddressId(guestAddress.id);
      setShowNewAddressForm(false);
      return;
    }

    // For logged-in users, save to backend
    try {
      const addressData: CreateAddressData = {
        full_name: newAddress.full_name,
        phone_number: newAddress.phone_number,
        address_line1: newAddress.address_line1,
        address_line2: newAddress.address_line2,
        city: newAddress.city,
        state: newAddress.state,
        postal_code: newAddress.postal_code,
        country: newAddress.country,
        address_type: newAddress.address_type,
        is_default: newAddress.is_default,
      };

      const created = await checkoutService.createAddress(addressData);
      setAddresses([...addresses, created]);
      setSelectedAddressId(created.id);
      setShowNewAddressForm(false);

      // Reset form
      setNewAddress({
        full_name: '',
        phone_number: '',
        address_line1: '',
        address_line2: '',
        city: '',
        state: '',
        postal_code: '',
        country: 'Nigeria',
        address_type: 'shipping',
        is_default: false,
      });
    } catch (error: any) {
      console.error('Error creating address:', error);
      alert(error.response?.data?.detail || 'Failed to create address. Please try again.');
    }
  };

  const handleCalculateShipping = async () => {
    const selectedAddress = addresses.find(addr => addr.id === selectedAddressId);
    if (!selectedAddress) return;

    setIsLoadingShipping(true);
    try {
      const data = await checkoutService.calculateShipping({
        country: selectedAddress.country,
        state: selectedAddress.state,
        order_value: cart.summary.subtotal,
      });

      setShippingRates(data.available_rates);

      // Auto-select recommended or first rate
      if (data.recommended_rate) {
        setSelectedShippingRateId(data.recommended_rate.id);
      } else if (data.available_rates.length > 0) {
        setSelectedShippingRateId(data.available_rates[0].id);
      }
    } catch (error) {
      console.error('Error calculating shipping:', error);
      alert('Failed to calculate shipping rates. Please try again.');
    } finally {
      setIsLoadingShipping(false);
    }
  };

  const handleApplyPromo = async () => {
    if (!promo.trim()) {
      setPromoError('Please enter a promo code');
      return;
    }

    setIsApplyingPromo(true);
    setPromoError('');

    try {
      const result = await checkoutService.validatePromoCode({
        code: promo,
        order_subtotal: cart.summary.subtotal,
      });

      if (result.valid && result.discount_amount) {
        setAppliedPromo({
          code: result.code!,
          discount_type: result.discount_type!,
          discount_value: result.discount_value!,
          discount_amount: result.discount_amount,
        });
        setPromoError('');
      } else {
        setAppliedPromo(null);
        setPromoError(result.message || 'Invalid promo code');
      }
    } catch (error: any) {
      console.error('Error validating promo code:', error);
      setAppliedPromo(null);
      setPromoError(error.response?.data?.detail || 'Failed to validate promo code');
    } finally {
      setIsApplyingPromo(false);
    }
  };

  const handleReviewOrder = async () => {
    if (!selectedAddressId) return;

    try {
      const items = cart.items.map(item => ({
        product_id: item.product_id,
        variant_id: item.variant.id,
        quantity: item.quantity,
      }));

      // Get selected address
      const selectedAddress = addresses.find(addr => addr.id === selectedAddressId);

      // Prepare request based on guest vs authenticated user
      const reviewRequest: any = {
        items,
        promo_code: appliedPromo?.code,
      };

      if (isGuestCheckout && selectedAddress && selectedAddress.id === 'guest-address') {
        // For guest checkout, send address data directly
        reviewRequest.guest_address = {
          full_name: selectedAddress.full_name,
          phone_number: selectedAddress.phone_number,
          address_line1: selectedAddress.address_line1,
          address_line2: selectedAddress.address_line2,
          city: selectedAddress.city,
          state: selectedAddress.state,
          postal_code: selectedAddress.postal_code,
          country: selectedAddress.country,
        };
      } else {
        // For authenticated users, send address ID
        reviewRequest.shipping_address_id = selectedAddressId;
      }

      const review = await checkoutService.reviewOrder(reviewRequest);

      setOrderReview(review);
    } catch (error) {
      console.error('Error reviewing order:', error);
      alert('Failed to review order. Please try again.');
    }
  };

  const handlePurchase = async () => {
    if (!selectedAddressId || !orderReview) return;

    const buildTrackingPath = (id: string) => ROUTES.ORDER_TRACKING.replace(':orderId', id);
    setIsCreatingOrder(true);
    try {
      const items = cart.items.map(item => ({
        product_id: item.product_id,
        variant_id: item.variant.id,
        quantity: item.quantity,
      }));

      // Get selected address
      const selectedAddress = addresses.find(addr => addr.id === selectedAddressId);

      // Prepare order request based on guest vs authenticated user
      const orderRequest: any = {
        items,
        promo_code: appliedPromo?.code,
      };

      if (isGuestCheckout && selectedAddress && selectedAddress.id === 'guest-address') {
        // For guest checkout, send address data and email directly
        orderRequest.guest_address = {
          full_name: selectedAddress.full_name,
          phone_number: selectedAddress.phone_number,
          address_line1: selectedAddress.address_line1,
          address_line2: selectedAddress.address_line2,
          city: selectedAddress.city,
          state: selectedAddress.state,
          postal_code: selectedAddress.postal_code,
          country: selectedAddress.country,
        };
        orderRequest.customer_email = email;
      } else {
        // For authenticated users, send address ID
        orderRequest.shipping_address_id = selectedAddressId;
        orderRequest.billing_address_id = selectedAddressId;
      }

      // Create order first
      const order = await checkoutService.createOrder(orderRequest);

      // Initialize payment with Paystack
      const paymentData = await paymentService.initializePayment({
        order_id: order.id,
        email: email || 'guest@shopsoma.com',
        callback_url: `${window.location.origin}/payment/verify`,
      });

      // Open Paystack popup
      const paystackPublicKey = import.meta.env.VITE_PAYSTACK_PUBLIC_KEY;
      const handler = window.PaystackPop.setup({
        key: paystackPublicKey,
        email: email || 'guest@shopsoma.com',
        amount: Math.round(orderReview.summary.total_amount * 100), // Amount in kobo
        currency: 'NGN',
        ref: paymentData.reference,
        callback: (response: any) => {
          // Payment successful - handle async operations
          console.log('Payment successful:', response);

          // Verify payment and navigate (fire and forget)
          paymentService.verifyPayment({
            reference: response.reference,
          }).then(() => {
            // Clear cart
            CartService.clearCart();

            // Navigate to order confirmation with success status
            navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=success`);
          }).catch((error) => {
            console.error('Payment verification error:', error);
            navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=verification_failed`);
          });
        },
        onClose: () => {
          console.log('Payment popup closed');
          setIsCreatingOrder(false);
          alert('Payment cancelled. You can retry payment from your orders page.');
          navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=cancelled`);
        },
      });

      handler.openIframe();
    } catch (error: any) {
      console.error('Error creating order:', error);
      alert(error.response?.data?.detail || 'Failed to create order. Please try again.');
      setIsCreatingOrder(false);
    }
  };

  // Email validation regex
  const isValidEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const hasEmail = email.trim().length > 3 && isValidEmail(email);
  const hasSelectedAddress = !!selectedAddressId;
  const hasSelectedShipping = !!selectedShippingRateId;
  const canPurchase = step === 'payment' && hasEmail && hasSelectedAddress && hasSelectedShipping && orderReview;

  const selectedShippingRate = shippingRates.find(rate => rate.id === selectedShippingRateId);

  const goBackToBag = () => navigate(ROUTES.CART);

  const handleEmailConfirm = () => {
    setEmailError('');

    if (!email.trim()) {
      setEmailError('Please enter your email address');
      return;
    }

    if (!isValidEmail(email)) {
      setEmailError('Please enter a valid email address');
      return;
    }

    setIsEmailConfirmed(true);
    setIsEditingEmail(false);
    setStep('address');
  };

  const handleEditEmail = () => {
    setIsEditingEmail(true);
    setIsEmailConfirmed(false);
  };

  const handleAddressSave = async () => {
    if (hasSelectedAddress) {
      await handleCalculateShipping();
      setStep('shipping');
    }
  };

  const handleShippingSave = async () => {
    await handleReviewOrder();
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
                {/* Email Step */}
                <div className="space-y-3">
                  {renderStepTitle('Your Email', true)}
                  <div className="max-w-2xl space-y-2">
                    {isEmailConfirmed && !isEditingEmail ? (
                      // Confirmed email display
                      <div className="flex items-center justify-between py-2 border-b border-gray-200">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{email}</span>
                          <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded">✓ Confirmed</span>
                          {isGuestCheckout && (
                            <span className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded">Guest</span>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={handleEditEmail}
                          className="text-xs text-primary underline hover:text-primary-dark"
                        >
                          Edit
                        </button>
                      </div>
                    ) : (
                      // Email input mode
                      <>
                        <div className="flex items-end gap-4">
                          <div className="flex-1">
                            <label className="text-xs text-gray-500">Email</label>
                            <input
                              type="email"
                              value={email}
                              onChange={(e) => {
                                setEmail(e.target.value);
                                setEmailError('');
                              }}
                              onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                  handleEmailConfirm();
                                }
                              }}
                              className={`w-full px-3 py-2 text-sm rounded-sm border ${emailError ? 'border-red-500' : 'border-gray-300'} focus:border-primary focus:outline-none`}
                              placeholder="you@example.com"
                              autoFocus={isEditingEmail}
                            />
                          </div>
                          <button
                            type="button"
                            onClick={handleEmailConfirm}
                            disabled={!hasEmail}
                            className="px-6 py-2 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50 hover:bg-primary-dark transition"
                          >
                            Confirm
                          </button>
                        </div>
                        {emailError && (
                          <p className="text-xs text-red-500">{emailError}</p>
                        )}
                        {!isEmailConfirmed && isGuestCheckout && (
                          <div className="pt-3 flex items-center justify-between text-xs">
                            <span className="text-gray-600">
                              Already have an account?{' '}
                              <Link to="/login" className="text-primary font-semibold hover:underline">
                                Sign in
                              </Link>
                            </span>
                            <span className="text-gray-400">or continue as guest</span>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* Address Step */}
                <div className="space-y-4">
                  {renderStepTitle('Addresses', step !== 'email')}
                  {step === 'address' || step === 'shipping' || step === 'payment' ? (
                    <div className="space-y-3 max-w-2xl">
                      {isGuestCheckout && !showNewAddressForm && addresses.length === 0 && (
                        <div className="bg-gray-50 border border-gray-200 p-4 rounded-sm space-y-2">
                          <p className="text-xs text-gray-600">
                            <span className="font-semibold">Guest Checkout</span>
                            {' - '}You're checking out as a guest.
                            <Link to="/signup" className="text-primary font-semibold hover:underline ml-1">
                              Create an account
                            </Link>
                            {' '}to save your address for faster checkout next time.
                          </p>
                        </div>
                      )}
                      {isLoadingAddresses ? (
                        <p className="text-sm text-gray-500">Loading addresses...</p>
                      ) : (
                        <>
                          {/* Existing Addresses */}
                          {addresses.filter(addr => addr.address_type === 'shipping').map((addr) => (
                            <button
                              key={addr.id}
                              type="button"
                              onClick={() => setSelectedAddressId(addr.id)}
                              className={`w-full text-left border border-gray-200 px-4 py-3 rounded-sm ${
                                selectedAddressId === addr.id ? 'bg-gray-50 border-primary' : ''
                              }`}
                            >
                              <p className="text-sm font-semibold text-gray-800">{addr.full_name}</p>
                              <p className="text-xs text-gray-600">
                                {addr.address_line1}, {addr.city}, {addr.state}, {addr.country}
                              </p>
                              <p className="text-xs text-gray-500">{addr.phone_number}</p>
                            </button>
                          ))}

                          {/* New Address Form */}
                          {showNewAddressForm ? (
                            <div className="border border-gray-200 p-4 rounded-sm space-y-3">
                              <h3 className="text-sm font-semibold text-gray-800">New Address</h3>
                              <div>
                                <label className="text-xs text-gray-500">Full Name</label>
                                <input
                                  type="text"
                                  value={newAddress.full_name}
                                  onChange={(e) => setNewAddress({ ...newAddress, full_name: e.target.value })}
                                  className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500">Phone</label>
                                <input
                                  type="tel"
                                  value={newAddress.phone_number}
                                  onChange={(e) => setNewAddress({ ...newAddress, phone_number: e.target.value })}
                                  className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500">Street Address</label>
                                <input
                                  type="text"
                                  value={newAddress.address_line1}
                                  onChange={(e) => setNewAddress({ ...newAddress, address_line1: e.target.value })}
                                  className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                />
                              </div>
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <label className="text-xs text-gray-500">City</label>
                                  <input
                                    type="text"
                                    value={newAddress.city}
                                    onChange={(e) => setNewAddress({ ...newAddress, city: e.target.value })}
                                    className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                  />
                                </div>
                                <div>
                                  <label className="text-xs text-gray-500">State</label>
                                  <input
                                    type="text"
                                    value={newAddress.state}
                                    onChange={(e) => setNewAddress({ ...newAddress, state: e.target.value })}
                                    className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                  />
                                </div>
                              </div>
                              <div className="pt-2">
                                <label className="inline-flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={newAddress.is_default}
                                    onChange={(e) => setNewAddress({ ...newAddress, is_default: e.target.checked })}
                                    className="h-4 w-4 border-gray-400 text-primary focus:ring-primary"
                                  />
                                  Set as default shipping address
                                </label>
                              </div>
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  onClick={handleCreateAddress}
                                  className="flex-1 py-2 rounded-sm bg-primary text-white text-sm font-semibold"
                                >
                                  Save Address
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setShowNewAddressForm(false)}
                                  className="px-4 py-2 rounded-sm border border-gray-300 text-sm"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setShowNewAddressForm(true)}
                              className="w-full py-3 border border-dashed border-gray-300 rounded-sm text-sm text-gray-600 hover:border-primary hover:text-primary"
                            >
                              + Add New Address
                            </button>
                          )}

                          <div className="pt-4">
                            <button
                              type="button"
                              onClick={handleAddressSave}
                              disabled={!hasSelectedAddress || isLoadingShipping}
                              className="w-full py-3 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
                            >
                              {isLoadingShipping ? 'Calculating Shipping...' : 'Continue'}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  ) : (
                    <p className="text-gray-300 text-sm">Addresses</p>
                  )}
                </div>

                {/* Shipping Step */}
                <div className="space-y-4">
                  {renderStepTitle('Shipping Method', step === 'shipping' || step === 'payment')}
                  {step === 'shipping' || step === 'payment' ? (
                    <div className="space-y-3">
                      {shippingRates.map((rate) => (
                        <button
                          key={rate.id}
                          type="button"
                          onClick={() => setSelectedShippingRateId(rate.id)}
                          className={`w-full text-left border border-gray-200 px-4 py-3 flex items-center gap-4 ${
                            selectedShippingRateId === rate.id ? 'bg-gray-50 border-primary' : ''
                          }`}
                        >
                          <div className="w-12 h-12 border border-gray-300 rounded flex items-center justify-center text-gray-500 text-sm">
                            📦
                          </div>
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-gray-800">{rate.name}</p>
                            <p className="text-xs text-gray-500">
                              {rate.description} ({rate.min_delivery_days} - {rate.max_delivery_days} business days)
                            </p>
                          </div>
                          <p className="text-sm font-semibold text-gray-800">₦{rate.base_rate.toLocaleString()}</p>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={handleShippingSave}
                        disabled={!hasSelectedShipping}
                        className="px-6 py-2 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
                      >
                        Continue
                      </button>
                    </div>
                  ) : (
                    <p className="text-gray-300 text-sm">Shipping Method</p>
                  )}
                </div>

                {/* Payment Step */}
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
                        onClick={handlePurchase}
                        disabled={!canPurchase || isCreatingOrder}
                        className="w-full py-3 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
                      >
                        {isCreatingOrder ? 'Processing...' : 'Purchase'}
                      </button>
                    </div>
                  ) : (
                    <p className="text-gray-300 text-sm">Payment Method</p>
                  )}
                </div>
              </div>
            </div>

            {/* Order Summary Sidebar */}
            <aside className="border border-gray-200 rounded-sm p-5 space-y-4 sticky top-6 h-fit">
              <div className="flex items-center justify-between text-sm font-semibold text-gray-800">
                <span>Order</span>
              </div>
              <div className="text-sm text-gray-700 space-y-2">
                <div className="flex items-center justify-between">
                  <span>Subtotal</span>
                  <span>₦{(orderReview?.summary.subtotal ?? cart.summary.subtotal).toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Shipping cost</span>
                  <span>₦{(orderReview?.summary.shipping_cost ?? (selectedShippingRate?.base_rate || 0)).toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Tax (VAT 7.5%)</span>
                  <span>₦{Number(orderReview?.summary.tax_amount ?? 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
                {(appliedPromo || (orderReview?.summary.discount_amount ?? 0) > 0) && (
                  <div className="flex items-center justify-between text-primary">
                    <span>Promo {appliedPromo && `(${appliedPromo.code})`}</span>
                    <span>-₦{(orderReview?.summary.discount_amount ?? appliedPromo?.discount_amount ?? 0).toLocaleString()}</span>
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
                    disabled={isApplyingPromo}
                    className="px-4 py-2 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
                  >
                    {isApplyingPromo ? '...' : 'Apply'}
                  </button>
                </div>
                {promoError && (
                  <p className="text-xs text-red-500">{promoError}</p>
                )}
                {appliedPromo && !promoError && (
                  <p className="text-xs text-green-600">
                    Promo applied! {appliedPromo.discount_type === 'percentage'
                      ? `${appliedPromo.discount_value}% off`
                      : `₦${appliedPromo.discount_value.toLocaleString()} off`}
                  </p>
                )}
              </div>
              <div className="flex items-center justify-between text-sm font-semibold text-gray-800 border-t border-gray-200 pt-3">
                <span>Total</span>
                <span>₦{Number(orderReview?.summary.total_amount ?? cart.summary.total).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
              <button
                className={`w-full py-3 rounded-sm text-sm font-semibold ${
                  canPurchase ? 'bg-primary text-white hover:bg-primary-dark transition' : 'bg-gray-200 text-gray-500'
                }`}
                disabled={!canPurchase || isCreatingOrder}
                onClick={handlePurchase}
              >
                {isCreatingOrder ? 'Processing...' : 'Purchase'}
              </button>
            </aside>
          </div>
        </div>
      </section>
    </Layout>
  );
}
