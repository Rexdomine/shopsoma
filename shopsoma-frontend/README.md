# Shopsoma Frontend

Multi-vendor marketplace for African fashion - Customer & Vendor Interface

## Project Overview

Shopsoma connects African fashion designers with global buyers. This React-based frontend provides:
- Customer shopping experience (browse, cart, checkout)
- Vendor dashboard (product management, orders, analytics)
- Admin interface (vendor approval, operations management)

**Launch Target:** December 12, 2025
**Tech Stack:** React, TypeScript, Vite, TailwindCSS

## Prerequisites

- Node.js 18+ and npm/yarn
- Git

## Getting Started

### 1. Clone the Repository

```bash
git clone <repository-url>
cd shopsoma-frontend
```

### 2. Install Dependencies

```bash
npm install
```

### 3. Environment Setup

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Configure the following environment variables:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_your_key
VITE_PAYSTACK_PUBLIC_KEY=pk_test_your_key
```

### 4. Run Development Server

```bash
npm run dev
```

The application will be available at `http://localhost:5173`

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript type checking
- `npm test` - Run tests

## Project Structure

```
shopsoma-frontend/
├── src/
│   ├── assets/          # Images, fonts, static files
│   ├── components/      # Reusable UI components
│   │   ├── common/      # Buttons, inputs, cards
│   │   ├── customer/    # Customer-specific components
│   │   ├── vendor/      # Vendor dashboard components
│   │   └── admin/       # Admin interface components
│   ├── pages/           # Page components
│   │   ├── customer/    # Shopping pages
│   │   ├── vendor/      # Vendor dashboard
│   │   └── admin/       # Admin panel
│   ├── hooks/           # Custom React hooks
│   ├── api/             # API client and services
│   ├── store/           # State management (Redux/Zustand)
│   ├── types/           # TypeScript type definitions
│   ├── utils/           # Helper functions
│   ├── styles/          # Global styles and themes
│   ├── App.tsx          # Main app component
│   └── main.tsx         # Entry point
├── public/              # Public static assets
├── .github/             # GitHub workflows, PR templates
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Urgent production fixes

### Making Changes

1. Create a feature branch from `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit:
   ```bash
   git add .
   git commit -m "feat: add product filtering"
   ```

3. Push and create a Pull Request to `develop`:
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Convention

Follow conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

## Code Style

- Follow ESLint and Prettier configurations
- Use TypeScript for type safety
- Write meaningful component and variable names
- Add comments for complex logic
- Keep components small and focused

## Testing

```bash
# Run all tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run tests with coverage
npm test -- --coverage
```

## Building for Production

```bash
npm run build
```

The built files will be in the `dist/` directory.

## Deployment

The frontend is deployed on Render:
- **Production:** Deploys from `main` branch
- **Staging:** Deploys from `develop` branch

### Manual Deployment

```bash
npm run build
# Upload dist/ to hosting service
```

## Key Features

### Customer Features
- Product browsing and search
- Shopping cart management
- Secure checkout (Stripe/Paystack)
- Order tracking
- User profile management

### Vendor Features
- Product inventory management
- CSV bulk upload
- Order management
- Sales analytics (7/30-day views)
- Payout tracking

### Admin Features
- Vendor approval workflow
- Product moderation
- Order oversight
- Payout management
- Platform analytics

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `VITE_API_BASE_URL` | Backend API URL | Yes |
| `VITE_STRIPE_PUBLISHABLE_KEY` | Stripe public key | Yes |
| `VITE_PAYSTACK_PUBLIC_KEY` | Paystack public key | Yes |

## Troubleshooting

### Port Already in Use
```bash
# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

### TypeScript Errors
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

## Contributing

1. Follow the PR template when submitting changes
2. Ensure all tests pass
3. Request review from code owners
4. Address review comments promptly

## Team

- **Project Manager:** Rex
- **Design Lead:** Chisom
- **Vendor Operations:** Maryam Sulaiman

## License

Proprietary - Shopsoma 2025

## Support

For questions or issues, contact the development team or create an issue in the repository.

---

**Shopsoma** - Connecting African Fashion with the World
