import { Link } from 'react-router-dom';

export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-border-subtle bg-surface-base">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid gap-8 sm:grid-cols-3">
          <div>
            <h3 className="mb-3 text-sm font-semibold text-text-primary">Project</h3>
            <p className="text-sm text-text-muted">Experimental, unaudited open-source software.</p>
          </div>
          <div>
            <h3 className="mb-3 text-sm font-semibold text-text-primary">Learn</h3>
            <ul className="space-y-2">
              <li>
                <Link to="/about" className="text-sm text-text-muted hover:text-text-primary">
                  About
                </Link>
              </li>
              <li>
                <Link to="/features" className="text-sm text-text-muted hover:text-text-primary">
                  Features
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="mb-3 text-sm font-semibold text-text-primary">Use</h3>
            <p className="text-sm text-text-muted">Local development and public testnets only.</p>
          </div>
        </div>
        <div className="mt-10 border-t border-border-subtle pt-6 text-center text-xs text-text-muted">
          <p>&copy; {currentYear} Ledova contributors. Apache-2.0.</p>
        </div>
      </div>
    </footer>
  );
}
