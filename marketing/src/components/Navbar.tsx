import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { List as ListIcon, X as XIcon } from '@phosphor-icons/react';

const NAV_LINKS = [
  { label: 'Home', path: '/' },
  { label: 'Features', path: '/features' },
  { label: 'About', path: '/about' },
  { label: 'Contact', path: '/contact' },
];

const GITHUB_URL = 'https://github.com/RonildoBraga/ledova';

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border-subtle bg-surface-base/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <img src="/icons/logo.png" alt="Ledova" className="h-8 w-8 object-contain" />
          <span className="text-lg font-semibold text-text-primary">Ledova</span>
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              className={`text-sm transition-colors ${
                location.pathname === link.path
                  ? 'font-medium text-brand-light'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:text-brand-light"
          >
            GitHub
          </a>
          <Link
            to="/contact"
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-hover"
          >
            Contact Us
          </Link>
        </div>

        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="text-text-muted md:hidden"
          aria-label="Toggle menu"
        >
          {mobileOpen ? <XIcon size={24} /> : <ListIcon size={24} />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-border-subtle bg-surface-base px-6 pb-6 pt-4 md:hidden">
          <div className="flex flex-col gap-4">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                onClick={() => setMobileOpen(false)}
                className={`text-sm ${
                  location.pathname === link.path ? 'font-medium text-brand-light' : 'text-text-muted'
                }`}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-2 flex flex-col gap-3 border-t border-border-subtle pt-4">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                className="text-center text-sm font-medium text-text-primary"
              >
                GitHub
              </a>
              <Link
                to="/contact"
                onClick={() => setMobileOpen(false)}
                className="rounded-lg bg-brand px-4 py-2.5 text-center text-sm font-medium text-white"
              >
                Contact Us
              </Link>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
