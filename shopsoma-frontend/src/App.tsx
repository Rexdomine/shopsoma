import { useEffect } from 'react';
import { AuthProvider } from './context/AuthContext';
import AppRouter from './router';
import ErrorBoundary from './components/error/ErrorBoundary';
import { useCurrencyStore } from './store/currencyStore';
import './App.css';

function App() {
  const fetchExchangeRate = useCurrencyStore((state) => state.fetchExchangeRate);

  // Fetch exchange rate on app initialization
  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
