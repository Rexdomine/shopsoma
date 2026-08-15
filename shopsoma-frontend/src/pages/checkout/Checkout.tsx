import { useState, useEffect } from 'react';
import { buildPaystackWidgetConfig, type PaymentGateway, type InitializePaymentResponse } from '../../services/paymentService';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import { checkoutService, type Address, type ShippingRate, type OrderReview, type CreateAddressData, type CheckoutEstimate, type Order } from '../../services/checkoutService';
import { CartService } from '../../services/cartService';
import { paymentService } from '../../services/paymentService';
import { useAuth } from '../../context/AuthContext';
import { usePreferenceStore } from '../../store/preferenceStore';
import { useCurrencyStore } from '../../store/currencyStore';
import { useCartStore } from '../../store/cartStore';
import { convertCurrencyWithRates, formatPriceWithConversion, type Currency } from '../../utils/pricing';
import { loadStripe } from '@stripe/stripe-js';
import { Elements } from '@stripe/react-stripe-js';
import StripePaymentForm from '../../components/payment/StripePaymentForm';
import CheckoutEstimateSelector from './CheckoutEstimateSelector';

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

const ALL_PAYMENT_OPTIONS: { id: PaymentGateway; name: string; icon: string; supportedCurrencies: Currency[] }[] = [
  { id: 'paystack', name: 'Paystack', icon: '/images/paystack.svg', supportedCurrencies: ['NGN'] },
  { id: 'stripe', name: 'Stripe', icon: '/images/stripe.svg', supportedCurrencies: ['NGN', 'USD'] },
];

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '');

export default function Checkout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, isAuthenticated } = useAuth();
  const { currency, setCurrency } = usePreferenceStore();
  const exchangeRates = useCurrencyStore((state) => state.exchangeRates);

  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [isEmailConfirmed, setIsEmailConfirmed] = useState(false);
  const [isEditingEmail, setIsEditingEmail] = useState(false);
  const [isGuestCheckout, setIsGuestCheckout] = useState(false);

  // Use cart from store so it updates when synced after login
  const cart = useCartStore((state) => state.cart);

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
  const [paymentMethod, setPaymentMethod] = useState<PaymentGateway>('paystack');
  const [stripeClientSecret, setStripeClientSecret] = useState<string>('');
  const [stripePaymentIntentId, setStripePaymentIntentId] = useState<string>('');
  const [showStripePaymentModal, setShowStripePaymentModal] = useState(false);
  const [currentOrderId, setCurrentOrderId] = useState<string>('');
  const [enforcedOrder, setEnforcedOrder] = useState<Order | null>(null);
  const [checkoutEstimate, setCheckoutEstimate] = useState<CheckoutEstimate | null>(null);
  const [checkoutCapability, setCheckoutCapability] = useState<string | undefined>();
  const [, setEstimateRequestKey] = useState<string>('');
  const [selectionKeys] = useState(() => new Map<string, string>());

  const newIdempotencyKey = (prefix: string) => `${prefix}-${crypto.randomUUID()}`;

  // Filter payment options based on currency
  const paymentOptions = ALL_PAYMENT_OPTIONS.filter(option =>
    option.supportedCurrencies.includes(currency)
  );

  // Auto-select first available payment method when currency changes
  useEffect(() => {
    const currentMethodSupported = paymentOptions.some(option => option.id === paymentMethod);
    if (!currentMethodSupported && paymentOptions.length > 0) {
      setPaymentMethod(paymentOptions[0].id);
    }
  }, [currency, paymentMethod, paymentOptions]);

  // Loading states
  const [isLoadingAddresses, setIsLoadingAddresses] = useState(false);
  const [isLoadingShipping, setIsLoadingShipping] = useState(false);
  const [isReviewingOrder, setIsReviewingOrder] = useState(false);
  const [isApplyingPromo, setIsApplyingPromo] = useState(false);
  const [isCreatingOrder, setIsCreatingOrder] = useState(false);

  // Email validation state
  const [emailError, setEmailError] = useState('');

  const cartSubtotalInNgn = cart.items.reduce((sum, item) => {
    return sum + convertCurrencyWithRates(
      item.subtotal,
      item.product.currency || 'NGN',
      'NGN',
      exchangeRates
    );
  }, 0);

  const cartSubtotalInSelectedCurrency = cart.items.reduce((sum, item) => {
    return sum + convertCurrencyWithRates(
      item.subtotal,
      item.product.currency || 'NGN',
      currency,
      exchangeRates
    );
  }, 0);

  // Prefill user data on mount if authenticated
  useEffect(() => {
    if (isAuthenticated && user) {
      // Prefill email
      setEmail(user.email);
      setIsEmailConfirmed(true);
      setStep('address');

      // Load saved addresses
      loadAddresses();
    } else {
      // Guest checkout
      setIsGuestCheckout(true);
    }
  }, [isAuthenticated, user]);

  useEffect(() => {
    if (isAuthenticated) return;
    const stateEmail = (location.state as any)?.guestEmail as string | undefined;
    const storedEmail = sessionStorage.getItem('shopsoma_guest_email') || undefined;
    const params = new URLSearchParams(location.search);
    const hasGuestFlag = params.get('guest') === '1';
    const prefillEmail = stateEmail || storedEmail;

    if (prefillEmail) {
      setEmail(prefillEmail);
      setIsGuestCheckout(true);
    }

    if (hasGuestFlag) {
      setIsGuestCheckout(true);
    }
  }, [isAuthenticated, location.search, location.state]);

  const loadAddresses = async () => {
    setIsLoadingAddresses(true);
    try {
      const data = await checkoutService.getAddresses();
      setAddresses(data.addresses);

      // Auto-select default address if exists
      const defaultAddr = data.addresses.find(addr => addr.is_default && addr.address_type === 'shipping');
      if (defaultAddr) {
        setSelectedAddressId(defaultAddr.id);

        // Prefill new address form with user's name and phone from default address
        if (user) {
          setNewAddress(prev => ({
            ...prev,
            full_name: defaultAddr.full_name,
            phone_number: defaultAddr.phone_number,
          }));
        }
      } else if (user) {
        // If no default address, prefill form with user's basic info
        setNewAddress(prev => ({
          ...prev,
          full_name: user.full_name || '',
          phone_number: user.phone_number || '',
        }));
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
        full_name: user?.full_name || '',
        phone_number: user?.phone_number || '',
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
        order_value: cartSubtotalInNgn,
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
        order_subtotal: cartSubtotalInNgn,
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

  const handleReviewOrder = async (): Promise<OrderReview | null> => {
    if (!selectedAddressId) return null;

    try {
      const items = cart.items.map(item => ({
        product_id: item.product_id,
        variant_id: item.variant?.id?.startsWith('default-') ? null : item.variant?.id,
        quantity: item.quantity,
      }));

      // Get selected address
      const selectedAddress = addresses.find(addr => addr.id === selectedAddressId);

      // Prepare request based on guest vs authenticated user
      const reviewRequest: any = {
        items,
        currency,
        shipping_rate_id: selectedShippingRateId || undefined,
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
      return review;
    } catch (error) {
      console.error('Error reviewing order:', error);
      alert('Failed to review order. Please try again.');
      return null;
    }
  };

  const clearCheckoutCapability = () => setCheckoutCapability(undefined);

  const openInitializedPayment = (
    order: Order,
    paymentData: InitializePaymentResponse,
  ) => {
    if (paymentMethod === 'paystack') {
      const widgetTruth = buildPaystackWidgetConfig(paymentData, {
        key: import.meta.env.VITE_PAYSTACK_PUBLIC_KEY,
        email: email || 'guest@shopsoma.com',
      });
      const handler = window.PaystackPop.setup({
        ...widgetTruth,
        callback: (response: { reference: string }) => {
          paymentService.verifyPayment({
            reference: response.reference,
            payment_gateway: 'paystack',
          }).then(() => {
            clearCheckoutCapability();
            CartService.clearCart();
            navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=success`);
          }).catch((error) => {
            console.error('Payment verification error:', error);
            navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=verification_failed`);
          });
        },
        onClose: () => {
          clearCheckoutCapability();
          setIsCreatingOrder(false);
          alert('Payment cancelled. You can retry payment from your orders page.');
          navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=cancelled`);
        },
      });
      handler.openIframe();
    } else if (paymentMethod === 'stripe') {
      setStripeClientSecret(paymentData.provider_payload?.client_secret ?? paymentData.client_secret ?? '');
      setStripePaymentIntentId(paymentData.provider_payload?.payment_intent_id ?? paymentData.payment_intent_id ?? '');
      setCurrentOrderId(order.id);
      setShowStripePaymentModal(true);
      setIsCreatingOrder(false);
    } else {
      throw new Error(`Unsupported payment gateway: ${paymentMethod}`);
    }
  };

  const initializeOrderPayment = async (order: Order, capability?: string) => {
    setIsCreatingOrder(true);
    try {
      const enforced = order.workflow_cohort === 'domestic_checkout_v1';
      const paymentData = await paymentService.initializePayment({
        order_id: order.id,
        email: email || 'guest@shopsoma.com',
        payment_gateway: paymentMethod,
        ...(enforced ? {} : { currency }),
        callback_url: `${window.location.origin}/payment/verify`,
      }, enforced ? capability : undefined);
      openInitializedPayment(order, paymentData);
    } catch (error: any) {
      if (error.response?.status === 404) clearCheckoutCapability();
      const retryable = error.response?.status === 503;
      alert(retryable
        ? 'Payment setup is temporarily unavailable. Your order is not complete; please retry.'
        : error.response?.data?.detail || error.message || 'Failed to initialize payment.');
      setIsCreatingOrder(false);
    }
  };

  const handlePurchase = async () => {
    if (!selectedAddressId || !orderReview || enforcedOrder) return;

    setIsCreatingOrder(true);
    try {
      const items = cart.items.map(item => ({
        product_id: item.product_id,
        variant_id: item.variant?.id?.startsWith('default-') ? null : item.variant?.id,
        quantity: item.quantity,
      }));
      const selectedAddress = addresses.find(addr => addr.id === selectedAddressId);
      const orderRequest: any = {
        items,
        currency,
        shipping_rate_id: selectedShippingRateId || undefined,
        promo_code: appliedPromo?.code,
      };

      if (isGuestCheckout && selectedAddress?.id === 'guest-address') {
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
        orderRequest.shipping_address_id = selectedAddressId;
        orderRequest.billing_address_id = selectedAddressId;
      }

      const order = await checkoutService.createOrder(orderRequest);
      if (order.workflow_cohort !== 'domestic_checkout_v1') {
        await initializeOrderPayment(order);
        return;
      }

      const capability = order.checkout_capability ?? undefined;
      setCheckoutCapability(capability);
      setEnforcedOrder(order);
      const requestKey = newIdempotencyKey('estimate');
      setEstimateRequestKey(requestKey);
      const estimate = await checkoutService.createCheckoutEstimate(order.id, requestKey, capability);
      setCheckoutEstimate(estimate);
      setIsCreatingOrder(false);
    } catch (error: any) {
      if (error.response?.status === 404) clearCheckoutCapability();
      alert(error.response?.data?.detail || error.message || 'Failed to create order. Please try again.');
      setIsCreatingOrder(false);
    }
  };

  const refreshCheckoutEstimate = async () => {
    if (!enforcedOrder) throw new Error('Checkout order is unavailable');
    const requestKey = newIdempotencyKey('estimate');
    setEstimateRequestKey(requestKey);
    return checkoutService.createCheckoutEstimate(enforcedOrder.id, requestKey, checkoutCapability);
  };

  const recoverCheckoutEstimate = async () => {
    setIsCreatingOrder(true);
    try {
      const estimate = await refreshCheckoutEstimate();
      setCheckoutEstimate(estimate);
    } catch (error: any) {
      if (error.response?.status === 404) clearCheckoutCapability();
      alert(error.response?.data?.detail || 'Delivery options are still unavailable. Please retry.');
    } finally {
      setIsCreatingOrder(false);
    }
  };

  const selectCheckoutOption = async (estimateId: string, optionId: string) => {
    if (!enforcedOrder) throw new Error('Checkout order is unavailable');
    const identity = `${estimateId}:${optionId}`;
    const selectionKey = selectionKeys.get(identity) ?? newIdempotencyKey('selection');
    selectionKeys.set(identity, selectionKey);
    return checkoutService.selectCheckoutEstimateOption(
      enforcedOrder.id,
      estimateId,
      optionId,
      selectionKey,
      checkoutCapability,
    );
  };

  const handleStripePaymentSuccess = async () => {
    try {
      // Verify payment with backend
      await paymentService.verifyPayment({
        payment_intent_id: stripePaymentIntentId,
        payment_gateway: 'stripe',
      });

      // Clear cart and navigate to success
      clearCheckoutCapability();
      CartService.clearCart();
      setShowStripePaymentModal(false);
      navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${currentOrderId}&payment=success`);
    } catch (error) {
      console.error('Payment verification error:', error);
      setShowStripePaymentModal(false);
      navigate(`${ROUTES.ORDER_SUCCESS}?orderId=${currentOrderId}&payment=verification_failed`);
    }
  };

  const handleStripePaymentError = (error: string) => {
    console.error('Stripe payment error:', error);
    alert(`Payment failed: ${error}`);
    setIsCreatingOrder(false);
  };

  // Email validation regex
  const isValidEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const isValidNigerianPhone = (value: string): boolean => {
    const digits = value.replace(/\D/g, '');
    return /^(0|234)[789]\d{9}$/.test(digits);
  };

  const hasEmail = email.trim().length > 3 && isValidEmail(email);
  const isAddressComplete = Boolean(
    newAddress.full_name.trim() &&
    newAddress.phone_number.trim() &&
    isValidNigerianPhone(newAddress.phone_number) &&
    newAddress.address_line1.trim() &&
    newAddress.city.trim() &&
    newAddress.state.trim() &&
    newAddress.country.trim()
  );
  const missingAddressFields = [
    !newAddress.full_name.trim() ? 'full name' : '',
    !newAddress.address_line1.trim() ? 'street address' : '',
    !newAddress.city.trim() ? 'city' : '',
    !newAddress.state.trim() ? 'state' : '',
    !newAddress.country.trim() ? 'country' : '',
  ].filter(Boolean);
  const phoneSaveGuidance = !newAddress.phone_number.trim()
    ? 'Enter a phone number so delivery partners can reach you.'
    : !isValidNigerianPhone(newAddress.phone_number)
      ? 'Complete the phone number in Nigerian format, e.g. 08012345678.'
      : '';
  const addressSaveGuidance = phoneSaveGuidance || (
    missingAddressFields.length
      ? `Complete ${missingAddressFields.join(', ')} to save this address.`
      : ''
  );
  const hasSelectedAddress = !!selectedAddressId;
  const hasSelectedShipping = !!selectedShippingRateId;
  const canPurchase = step === 'payment' && hasEmail && hasSelectedAddress && hasSelectedShipping && orderReview && !enforcedOrder;

  const selectedShippingRate = shippingRates.find(rate => rate.id === selectedShippingRateId);
  const shippingRateInSelectedCurrency = selectedShippingRate
    ? convertCurrencyWithRates(Number(selectedShippingRate.base_rate), 'NGN', currency, exchangeRates)
    : 0;
  const promoDiscountInSelectedCurrency = appliedPromo
    ? convertCurrencyWithRates(Number(appliedPromo.discount_amount || 0), 'NGN', currency, exchangeRates)
    : 0;
  const reviewSummaryCurrency = orderReview?.summary.currency ?? 'NGN';

  // Calculate tax and total for checkout display (before order review is available)
  const TAX_RATE = 0.075; // 7.5% VAT
  const calculateCheckoutTax = () => {
    if (orderReview) return orderReview.summary.tax_amount;
    // Calculate tax on subtotal (before order review is created)
    const subtotal = cartSubtotalInSelectedCurrency;
    return Math.round(subtotal * TAX_RATE * 100) / 100;
  };

  const calculateCheckoutTotal = () => {
    if (orderReview) return orderReview.summary.total_amount;
    // Calculate total (before order review is created)
    const subtotal = Number(cartSubtotalInSelectedCurrency);
    const shipping = Number(shippingRateInSelectedCurrency);
    const tax = calculateCheckoutTax();
    const discount = Number(promoDiscountInSelectedCurrency);
    return subtotal + shipping + tax - discount;
  };

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

    if (isGuestCheckout) {
      sessionStorage.setItem('shopsoma_guest_email', email.trim());
    }
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
    setIsReviewingOrder(true);
    try {
      const review = await handleReviewOrder();
      if (review) {
        setStep('payment');
      }
    } finally {
      setIsReviewingOrder(false);
    }
  };

  const renderStepTitle = (label: string, active: boolean) => (
    <p className={`text-sm font-semibold uppercase tracking-[0.2em] ${active ? 'text-dark' : 'text-gray-300'}`}>
      {label}
    </p>
  );

  // Helper function to format price in selected currency
  const formatPrice = (amount: number, sourceCurrency: Currency = 'NGN') => {
    return formatPriceWithConversion(amount, sourceCurrency, currency, exchangeRates);
  };

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
          <div className="flex items-center justify-end gap-4">
            {/* Currency Switcher */}
            <div className="flex items-center gap-2 border border-gray-300 rounded-sm px-3 py-1.5">
              <button
                onClick={() => setCurrency('NGN')}
                className={`text-xs font-semibold transition ${
                  currency === 'NGN'
                    ? 'text-primary'
                    : 'text-gray-400 hover:text-gray-600'
                }`}
              >
                NGN
              </button>
              <span className="text-gray-300">|</span>
              <button
                onClick={() => setCurrency('USD')}
                className={`text-xs font-semibold transition ${
                  currency === 'USD'
                    ? 'text-primary'
                    : 'text-gray-400 hover:text-gray-600'
                }`}
              >
                USD
              </button>
            </div>
            <span className="text-sm text-gray-700">Secure Checkout</span>
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
                              <Link
                                to="/login"
                                state={{ from: { pathname: '/checkout' } }}
                                className="text-primary font-semibold hover:underline"
                              >
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
                            <Link
                              to={ROUTES.REGISTER}
                              state={{
                                from: { pathname: ROUTES.CHECKOUT },
                                prefillEmail: email,
                              }}
                              className="text-primary font-semibold hover:underline ml-1"
                            >
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
                            <div
                              key={addr.id}
                              className={`w-full border border-gray-200 px-4 py-3 rounded-sm flex items-start gap-4 ${
                                selectedAddressId === addr.id ? 'bg-gray-50 border-primary' : ''
                              }`}
                            >
                              <button
                                type="button"
                                onClick={() => setSelectedAddressId(addr.id)}
                                className="flex-1 text-left"
                              >
                                <p className="text-sm font-semibold text-gray-800">{addr.full_name}</p>
                                <p className="text-xs text-gray-600">
                                  {addr.address_line1}, {addr.city}, {addr.state}, {addr.country}
                                </p>
                                <p className="text-xs text-gray-500">{addr.phone_number}</p>
                              </button>
                              {isGuestCheckout && addr.id === 'guest-address' && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setNewAddress({
                                      full_name: addr.full_name,
                                      phone_number: addr.phone_number,
                                      address_line1: addr.address_line1,
                                      address_line2: addr.address_line2 || '',
                                      city: addr.city,
                                      state: addr.state,
                                      postal_code: addr.postal_code || '',
                                      country: addr.country,
                                      address_type: addr.address_type,
                                      is_default: addr.is_default,
                                    });
                                    setSelectedAddressId(addr.id);
                                    setShowNewAddressForm(true);
                                  }}
                                  className="text-xs font-ui uppercase tracking-[0.2em] text-primary hover:text-primary-dark"
                                >
                                  Edit
                                </button>
                              )}
                            </div>
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
                                  required
                                />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500">Phone number <span className="text-red-500">*</span></label>
                                <div className="flex items-center gap-2 border-b border-gray-300 focus-within:border-primary py-2">
                                  <span className="inline-flex items-center gap-2 text-xs font-ui text-gray-500">
                                    <span className="inline-flex h-4 w-6 overflow-hidden rounded-sm border border-gray-200">
                                      <span className="h-full w-2 bg-[#137a3a]" />
                                      <span className="h-full w-2 bg-white" />
                                      <span className="h-full w-2 bg-[#137a3a]" />
                                    </span>
                                    +234
                                  </span>
                                  <input
                                    type="tel"
                                    value={newAddress.phone_number}
                                    onChange={(e) => setNewAddress({ ...newAddress, phone_number: e.target.value })}
                                    className="w-full bg-transparent focus:outline-none text-sm"
                                    inputMode="tel"
                                    pattern="^(0|234)[789]\\d{9}$"
                                    title="Enter a valid Nigerian phone number (e.g. 08012345678 or 2348012345678)"
                                    placeholder="08012345678"
                                    required
                                  />
                                </div>
                                <p className={`mt-1 text-xs ${phoneSaveGuidance ? 'text-amber-700' : 'text-gray-500'}`}>
                                  {phoneSaveGuidance || 'Required for delivery updates. Use 08012345678 or 2348012345678.'}
                                </p>
                              </div>
                              <div>
                                <label className="text-xs text-gray-500">Street Address</label>
                                <input
                                  type="text"
                                  value={newAddress.address_line1}
                                  onChange={(e) => setNewAddress({ ...newAddress, address_line1: e.target.value })}
                                  className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                  required
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
                                    required
                                  />
                                </div>
                                <div>
                                  <label className="text-xs text-gray-500">State</label>
                                  <input
                                    type="text"
                                    value={newAddress.state}
                                    onChange={(e) => setNewAddress({ ...newAddress, state: e.target.value })}
                                    className="w-full border-b border-gray-300 focus:border-primary focus:outline-none py-2 text-sm"
                                    required
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
                                  disabled={!isAddressComplete}
                                  className="flex-1 py-2 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
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
                              {!isAddressComplete && addressSaveGuidance && (
                                <p className="text-xs text-amber-700">
                                  {addressSaveGuidance}
                                </p>
                              )}
                            </div>
                          ) : !isGuestCheckout || addresses.length === 0 ? (
                            <button
                              type="button"
                              onClick={() => setShowNewAddressForm(true)}
                              className="w-full py-3 border border-dashed border-gray-300 rounded-sm text-sm text-gray-600 hover:border-primary hover:text-primary"
                            >
                              + Add New Address
                            </button>
                          ) : null}

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
                          <p className="text-sm font-semibold text-gray-800">{formatPrice(rate.base_rate)}</p>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={handleShippingSave}
                        disabled={!hasSelectedShipping || isReviewingOrder}
                        aria-busy={isReviewingOrder}
                        className="px-6 py-2 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
                      >
                        {isReviewingOrder ? (
                          <>
                            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                            Reviewing...
                          </>
                        ) : (
                          'Continue'
                        )}
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
                      {enforcedOrder && checkoutEstimate && (
                        <CheckoutEstimateSelector
                          estimate={checkoutEstimate}
                          selectOption={selectCheckoutOption}
                          refreshEstimate={refreshCheckoutEstimate}
                          onSelectionConfirmed={(selectedEstimate) => {
                            setCheckoutEstimate(selectedEstimate);
                            void initializeOrderPayment(enforcedOrder, checkoutCapability);
                          }}
                        />
                      )}
                      {enforcedOrder && !checkoutEstimate && (
                        <div className="space-y-2">
                          <p role="status" className="text-sm text-amber-700">
                            Your order was saved, but delivery options are not ready. Retry without creating another order.
                          </p>
                          <button
                            type="button"
                            onClick={() => void recoverCheckoutEstimate()}
                            disabled={isCreatingOrder}
                            className="w-full py-2 border border-primary text-primary text-sm font-semibold disabled:opacity-50"
                          >
                            {isCreatingOrder ? 'Retrying delivery options…' : 'Retry delivery options'}
                          </button>
                        </div>
                      )}
                      {ALL_PAYMENT_OPTIONS.map((option) => {
                        const isSupported = option.supportedCurrencies.includes(currency);
                        return (
                          <label
                            key={option.id}
                            className={`flex items-center justify-between border px-4 py-3 ${
                              isSupported
                                ? `cursor-pointer border-gray-200 ${
                                    paymentMethod === option.id ? 'bg-gray-50 border-primary' : ''
                                  }`
                                : 'cursor-not-allowed border-gray-100 bg-gray-50 opacity-50'
                            }`}
                          >
                            <span className="flex items-center gap-3 text-sm">
                              <input
                                type="radio"
                                name="payment"
                                checked={paymentMethod === option.id}
                                onChange={() => isSupported && setPaymentMethod(option.id)}
                                disabled={!isSupported}
                                className="text-primary disabled:cursor-not-allowed disabled:opacity-50"
                              />
                              <span className={isSupported ? 'text-gray-800' : 'text-gray-400'}>
                                {option.name}
                                {!isSupported && (
                                  <span className="ml-2 text-xs text-gray-400">
                                    (Not available for {currency})
                                  </span>
                                )}
                              </span>
                            </span>
                            {option.icon && (
                              <img
                                src={option.icon}
                                alt={option.name}
                                className={`h-6 ${!isSupported ? 'grayscale' : ''}`}
                              />
                            )}
                          </label>
                        );
                      })}
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
                <span className="text-xs text-gray-500">Currency: {currency}</span>
              </div>
              <div className="text-sm text-gray-700 space-y-2">
                <div className="flex items-center justify-between">
                  <span>Subtotal</span>
                  <span>{formatPrice(orderReview?.summary.subtotal ?? cartSubtotalInSelectedCurrency, orderReview ? reviewSummaryCurrency : currency)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Shipping cost</span>
                  <span>{formatPrice(orderReview?.summary.shipping_cost ?? Number(shippingRateInSelectedCurrency), orderReview ? reviewSummaryCurrency : currency)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Tax (VAT 7.5%)</span>
                  <span>{formatPrice(calculateCheckoutTax(), orderReview ? reviewSummaryCurrency : currency)}</span>
                </div>
                {(appliedPromo || (orderReview?.summary.discount_amount ?? 0) > 0) && (
                  <div className="flex items-center justify-between text-primary">
                    <span>Promo {appliedPromo && `(${appliedPromo.code})`}</span>
                    <span>-{formatPrice(orderReview?.summary.discount_amount ?? promoDiscountInSelectedCurrency, orderReview ? reviewSummaryCurrency : currency)}</span>
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
                      : `${formatPrice(appliedPromo.discount_value)} off`}
                  </p>
                )}
              </div>
              <div className="flex items-center justify-between text-sm font-semibold text-gray-800 border-t border-gray-200 pt-3">
                <span>Total</span>
                <span>{formatPrice(calculateCheckoutTotal(), orderReview ? reviewSummaryCurrency : currency)}</span>
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

      {/* Stripe Payment Modal */}
      {showStripePaymentModal && stripeClientSecret && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-sm p-6 max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Complete Payment</h2>
              <button
                onClick={() => {
                  setShowStripePaymentModal(false);
                  setIsCreatingOrder(false);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            <Elements stripe={stripePromise} options={{ clientSecret: stripeClientSecret }}>
              <StripePaymentForm
                onSuccess={handleStripePaymentSuccess}
                onError={handleStripePaymentError}
                isProcessing={isCreatingOrder}
                setIsProcessing={setIsCreatingOrder}
              />
            </Elements>
          </div>
        </div>
      )}
    </Layout>
  );
}
