import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Footer } from './Footer';

export function Layout() {
  return (
    <div className="relative flex min-h-screen flex-col">
      <div
        className="pointer-events-none fixed inset-0 -z-10"
        style={{
          background: `linear-gradient(180deg,
            var(--color-surface-base) 0%,
            var(--color-surface-base) 40%,
            var(--color-surface-raised) 100%)`,
        }}
      />
      <Navbar />
      <main className="flex-1 pt-16">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
