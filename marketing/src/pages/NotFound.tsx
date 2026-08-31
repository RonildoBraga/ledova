import { Link } from 'react-router-dom';

export function NotFound() {
  return (
    <section className="pb-16 pt-24 lg:pt-32">
      <div className="mx-auto max-w-6xl px-6 text-center">
        <p className="text-6xl font-bold text-brand-light">404</p>
        <h1 className="mt-4 text-4xl font-bold text-text-primary sm:text-5xl">Page not found</h1>
        <p className="mt-4 text-lg text-text-muted">The page you&apos;re looking for doesn&apos;t exist.</p>
        <Link
          to="/"
          className="mt-8 inline-block rounded-xl bg-brand px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-hover"
        >
          Back to Home
        </Link>
      </div>
    </section>
  );
}
