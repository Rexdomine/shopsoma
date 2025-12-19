import { useState, useEffect } from 'react';
import {
  PaymentElement,
  useStripe,
  useElements
} from '@stripe/react-stripe-js';

interface StripePaymentFormProps {
  onSuccess: () => void;
  onError: (error: string) => void;
  isProcessing: boolean;
  setIsProcessing: (processing: boolean) => void;
}

export default function StripePaymentForm({
  onSuccess,
  onError,
  isProcessing,
  setIsProcessing
}: StripePaymentFormProps) {
  const stripe = useStripe();
  const elements = useElements();
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);

  // Debug: Log when Stripe and Elements are ready
  useEffect(() => {
    console.log('Stripe ready:', !!stripe);
    console.log('Elements ready:', !!elements);
    if (stripe && elements) {
      setIsLoading(false);
    }
  }, [stripe, elements]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      return;
    }

    setIsProcessing(true);
    setErrorMessage('');

    try {
      const { error: submitError } = await elements.submit();
      if (submitError) {
        setErrorMessage(submitError.message || 'An error occurred');
        setIsProcessing(false);
        onError(submitError.message || 'An error occurred');
        return;
      }

      const { error } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: `${window.location.origin}/order-success`,
        },
        redirect: 'if_required',
      });

      if (error) {
        setErrorMessage(error.message || 'Payment failed');
        setIsProcessing(false);
        onError(error.message || 'Payment failed');
      } else {
        onSuccess();
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'An unexpected error occurred');
      setIsProcessing(false);
      onError(err.message || 'An unexpected error occurred');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-sm text-gray-500">Loading payment form...</div>
        </div>
      ) : (
        <PaymentElement
          onReady={() => console.log('PaymentElement ready')}
          onLoadError={(event) => {
            console.error('PaymentElement load error:', event);
            const errorMessage = event.error?.message || 'Failed to load payment form';
            setErrorMessage(errorMessage);
          }}
        />
      )}

      {errorMessage && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-sm p-3">
          {errorMessage}
        </div>
      )}

      <button
        type="submit"
        disabled={!stripe || isProcessing || isLoading}
        className={`w-full py-3 rounded-sm text-sm font-semibold ${
          !stripe || isProcessing || isLoading
            ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
            : 'bg-primary text-white hover:bg-primary-dark transition'
        }`}
      >
        {isProcessing ? 'Processing...' : isLoading ? 'Loading...' : 'Pay Now'}
      </button>
    </form>
  );
}
