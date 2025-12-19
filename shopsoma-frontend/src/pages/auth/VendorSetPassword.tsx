import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Eye, EyeOff, Check, X, Lock } from 'lucide-react';
import { ROUTES, STORAGE_KEYS } from '../../config/constants';
import { vendorActivationService } from '../../services/vendorActivationService';

export default function VendorSetPassword() {
  const navigate = useNavigate();
  const location = useLocation();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Get token from navigation state
  const activationToken = location.state?.token || '';
  const vendorEmail = location.state?.email || '';

  // Password validation rules
  const hasMinLength = password.length >= 8;
  const hasUpperCase = /[A-Z]/.test(password);
  const hasLowerCase = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(password);
  const passwordsMatch = password === confirmPassword && password.length > 0;

  const isValid = hasMinLength && hasUpperCase && hasLowerCase && hasNumber && passwordsMatch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || isSubmitting) return;

    setIsSubmitting(true);
    setError('');

    try {
      const response = await vendorActivationService.setPassword(activationToken, password);

      // Store authentication tokens
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, response.access_token);
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, response.refresh_token);

      // Navigate to brand info settings to complete onboarding
      navigate(ROUTES.VENDOR_BRAND_INFO, { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to set password. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const ValidationItem = ({ isValid, text }: { isValid: boolean; text: string }) => (
    <div className="flex items-center gap-2 text-sm">
      {isValid ? (
        <Check className="h-4 w-4 text-green-600" />
      ) : (
        <X className="h-4 w-4 text-gray-300" />
      )}
      <span className={isValid ? 'text-green-600' : 'text-gray-500'}>{text}</span>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#F6F6F3] to-[#E8E8E3] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-display text-[#105E53] mb-2">SHOPSOMA</h1>
          <p className="text-sm text-gray-600 font-ui">Vendor Portal</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-3xl shadow-xl border border-gray-200 p-8 space-y-6">
          {/* Header */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center h-16 w-16 rounded-full bg-[#105E53]/10 mb-4">
              <Lock className="h-8 w-8 text-[#105E53]" />
            </div>
            <h2 className="text-2xl font-display text-gray-900">Create Your Password</h2>
            <p className="text-sm text-gray-600 font-ui">
              Set a secure password for your vendor account
            </p>
            {vendorEmail && (
              <p className="text-xs text-gray-500 font-ui">{vendorEmail}</p>
            )}
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Password Field */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 font-ui">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent transition font-ui"
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>

            {/* Confirm Password Field */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 font-ui">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent transition font-ui"
                  placeholder="Confirm your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showConfirmPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>

            {/* Password Requirements */}
            <div className="bg-gray-50 rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-gray-700 mb-2 font-ui">Password must contain:</p>
              <ValidationItem isValid={hasMinLength} text="At least 8 characters" />
              <ValidationItem isValid={hasUpperCase} text="One uppercase letter" />
              <ValidationItem isValid={hasLowerCase} text="One lowercase letter" />
              <ValidationItem isValid={hasNumber} text="One number" />
              <ValidationItem isValid={hasSpecialChar} text="One special character (!@#$%^&*)" />
              <ValidationItem isValid={passwordsMatch} text="Passwords match" />
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={!isValid || isSubmitting}
              className="w-full bg-[#105E53] text-white py-3 rounded-full font-ui text-sm tracking-wide hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl"
            >
              {isSubmitting ? 'Setting Password...' : 'Continue to Dashboard Setup'}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-500 mt-6 font-ui">
          By creating a password, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
}
