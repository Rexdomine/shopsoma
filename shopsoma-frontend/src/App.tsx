import { AuthProvider } from './context/AuthContext';
import AppRouter from './router';
import ErrorBoundary from './components/error/ErrorBoundary';
import './App.css';

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
