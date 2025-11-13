import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function HeroSection() {
  return (
    <section className="bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left Content */}
          <div className="space-y-6">
            <div className="space-y-4">
              <h1 className="text-4xl lg:text-5xl font-display font-bold text-dark leading-tight">
                New Household
                <br />
                Collection
              </h1>
              <p className="text-base font-body text-gray-600">
                Enhance the appearance of your space.
              </p>
            </div>

            <Link
              to="/products"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-full font-body font-semibold transition-all duration-200 shadow-lg hover:shadow-xl text-base bg-primary text-white hover:bg-primary-dark"
            >
              Shop Now
              <ArrowRight className="w-5 h-5" />
            </Link>

            {/* Stats */}
            <div className="flex gap-8 pt-6">
              <div>
                <div className="text-2xl font-display font-bold text-dark">200+</div>
                <div className="text-sm font-body text-gray-500">Products</div>
              </div>
              <div>
                <div className="text-2xl font-display font-bold text-dark">50+</div>
                <div className="text-sm font-body text-gray-500">Vendors</div>
              </div>
              <div>
                <div className="text-2xl font-display font-bold text-dark">1000+</div>
                <div className="text-sm font-body text-gray-500">Customers</div>
              </div>
            </div>
          </div>

          {/* Right Content - Product Showcase */}
          <div className="relative hidden lg:block">
            <div className="grid grid-cols-2 gap-4">
              {[
                '/images/hero/portrait-lesbian-couple-posing-together.jpg',
                '/images/hero/medium-shot-woman-posing.jpg',
                '/images/hero/happy-man-party-wearing-sunglasses.jpg',
                '/images/hero/portrait-cool-man-with-sunglasses-dancing.jpg',
              ].map((image, index) => (
                <div
                  key={image}
                  className="aspect-square rounded-2xl overflow-hidden bg-gray-100 shadow-lg"
                >
                  <img
                    src={image}
                    alt={`Curated look ${index + 1}`}
                    className="w-full h-full object-cover transition-transform duration-700 ease-out hover:scale-105"
                    loading="lazy"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
