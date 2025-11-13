import AppRouter from './router';
import ErrorBoundary from './components/error/ErrorBoundary';
import './App.css';

function App() {
  return (
    <ErrorBoundary>
      <AppRouter />
    </ErrorBoundary>
  );
}

export default App;
