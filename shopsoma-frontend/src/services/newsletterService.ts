import api from './api';

export interface NewsletterSubscribePayload {
  email: string;
  firstName?: string;
  lastName?: string;
  consent?: boolean;
}

export async function subscribeToNewsletter(data: NewsletterSubscribePayload): Promise<{ message: string }> {
  const response = await api.post('/newsletter/subscribe', {
    email: data.email,
    first_name: data.firstName,
    last_name: data.lastName,
    consent: data.consent ?? true,
  });
  return response.data;
}
