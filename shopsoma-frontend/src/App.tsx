import { useEffect } from 'react';
import { AuthProvider } from './context/AuthContext';
import AppRouter from './router';
import ErrorBoundary from './components/error/ErrorBoundary';
import { useCurrencyStore } from './store/currencyStore';
import { usePreferenceStore } from './store/preferenceStore';
import './App.css';

function App() {
  const { currentCurrency, setCurrency, fetchExchangeRate } = useCurrencyStore();
  const preferredCurrency = usePreferenceStore((state) => state.currency);

  // Fetch exchange rate on app initialization
  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  useEffect(() => {
    if (preferredCurrency !== currentCurrency) {
      setCurrency(preferredCurrency);
    }
  }, [preferredCurrency, currentCurrency, setCurrency]);

  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
