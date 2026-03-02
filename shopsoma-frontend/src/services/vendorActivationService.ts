import api from './api';

export interface InitiateActivationRequest {
  email: string;
}

export interface InitiateActivationResponse {
  message: string;
  masked_email?: string;
  token?: string;
  account_already_setup?: boolean;
  reset_password_url?: string;
  support_email?: string;
}

export interface VerifyOTPRequest {
  token: string;
  otp_code: string;
}

export interface VerifyOTPResponse {
  message: string;
  activation_token: string;
  email: string;
}

export interface SetPasswordRequest {
  activation_token: string;
  password: string;
}

export interface SetPasswordResponse {
  message: string;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ResendOTPRequest {
  token: string;
}

export const vendorActivationService = {
  /**
   * Initiate vendor activation - sends OTP to email
   */
  async initiateActivation(email: string): Promise<InitiateActivationResponse> {
    try {
      const response = await api.post('/vendor/activation/initiate', { email });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to initiate activation';
      throw new Error(message);
    }
  },

  /**
   * Verify OTP code and activate vendor account
   */
  async verifyOTP(token: string, otp_code: string): Promise<VerifyOTPResponse> {
    try {
      const response = await api.post('/vendor/activation/verify-otp', {
        token,
        otp_code
      });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to verify code';
      throw new Error(message);
    }
  },

  /**
   * Resend OTP code to vendor's email
   */
  async resendOTP(token: string): Promise<{ message: string; masked_email: string }> {
    try {
      const response = await api.post('/vendor/activation/resend-otp', { token });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to resend code';
      throw new Error(message);
    }
  },

  /**
   * Set vendor password after OTP verification
   */
  async setPassword(activation_token: string, password: string): Promise<SetPasswordResponse> {
    try {
      const response = await api.post('/vendor/activation/set-password', {
        activation_token,
        password
      });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to set password';
      throw new Error(message);
    }
  },
};
