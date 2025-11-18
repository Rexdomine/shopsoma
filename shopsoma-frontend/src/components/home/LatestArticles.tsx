import { Calendar, ArrowRight } from 'lucide-react';

interface Article {
  id: string;
  title: string;
  excerpt: string;
  category: string;
  date: string;
  image: string;
}

// Mock data - replace with API call when blog/articles feature is implemented
const articles: Article[] = [
  {
    id: '1',
    title: 'WHY AFRICAN FASHION IS NECESSARY',
    excerpt:
      'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor',
    category: 'Culture',
    date: 'SEP 13,2022',
    image: '/article-1.jpg',
  },
  {
    id: '2',
    title: 'WHY AFRICAN FASHION IS NECESSARY',
    excerpt:
      'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor',
    category: 'Culture',
    date: 'SEP 13,2022',
    image: '/article-2.jpg',
  },
];

export default function LatestArticles() {
  return (
    <section className="py-12 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-1">
              LATEST ARTICLES & NEWS
            </h2>
            <p className="text-sm text-gray-600">Stay updated with our latest stories</p>
          </div>

          <a
            href="/blog"
            className="hidden md:inline-flex items-center gap-2 px-7 py-3 border-2 border-primary text-primary bg-white text-sm font-body font-semibold hover:bg-primary hover:text-white hover:border-primary transition-all duration-200"
          >
            Browse Articles
            <ArrowRight className="w-4 h-4" />
          </a>
        </div>

        {/* Articles Grid */}
        <div className="grid md:grid-cols-2 gap-6">
          {articles.map((article) => (
            <a
              key={article.id}
              href={`/blog/${article.id}`}
              className="group bg-gray-50 overflow-hidden hover:shadow-md transition-shadow border border-gray-200"
            >
              {/* Article Image */}
              <div className="relative h-48 bg-gray-200 overflow-hidden">
                <img
                  src={article.image}
                  alt={article.title}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                  }}
                />

                {/* Category Badge */}
                <div className="absolute top-3 left-3">
                  <span className="bg-white text-gray-900 px-3 py-1 text-xs font-medium border border-gray-200">
                    {article.category}
                  </span>
                </div>
              </div>

              {/* Article Content */}
              <div className="p-4">
                {/* Date */}
                <div className="flex items-center gap-1 text-xs text-gray-500 mb-2">
                  <Calendar className="w-3 h-3" />
                  <span>{article.date}</span>
                </div>

                {/* Title */}
                <h3 className="text-base font-bold text-gray-900 mb-2 group-hover:text-primary transition-colors line-clamp-2">
                  {article.title}
                </h3>

                {/* Excerpt */}
                <p className="text-sm text-gray-600 mb-3 line-clamp-2">{article.excerpt}</p>

                {/* Read More Link */}
                <div className="flex items-center gap-1 text-primary text-sm font-medium">
                  Read More
                  <ArrowRight className="w-3 h-3" />
                </div>
              </div>
            </a>
          ))}
        </div>

        {/* Mobile Browse Button */}
        <div className="md:hidden text-center mt-6">
          <a
            href="/blog"
            className="inline-flex items-center gap-2 px-7 py-3 border-2 border-primary text-primary bg-white text-sm font-body font-semibold hover:bg-primary hover:text-white hover:border-primary transition-all duration-200"
          >
            Browse Articles
            <ArrowRight className="w-4 h-4" />
          </a>
        </div>
      </div>
    </section>
  );
}
