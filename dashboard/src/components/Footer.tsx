const MARKETING_URL = import.meta.env.VITE_MARKETING_URL || '';

interface FooterProps {
  minimal?: boolean;
}

export default function Footer({ minimal = false }: FooterProps) {
  const currentYear = new Date().getFullYear();

  if (minimal) {
    return (
      <footer className="relative mt-auto border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-6 text-center sm:px-6 lg:px-8">
          <p className="text-sm text-text-muted">&copy; {currentYear} Ledova contributors</p>
          <p className="text-xs text-text-body">Experimental software • local and public-testnet use only</p>
        </div>
      </footer>
    );
  }

  return (
    <footer className="relative mt-auto border-t border-border">
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="grid gap-8 sm:grid-cols-2">
          <div>
            <h4 className="mb-3 font-semibold text-text-primary">Project</h4>
            <p className="text-sm text-text-body">Experimental, unaudited open-source software.</p>
          </div>
          <div>
            <h4 className="mb-3 font-semibold text-text-primary">Learn</h4>
            <div className="space-x-4">
              <a href={`${MARKETING_URL}/about`} className="text-sm text-text-body hover:text-text-primary">
                About
              </a>
              <a href={`${MARKETING_URL}/features`} className="text-sm text-text-body hover:text-text-primary">
                Features
              </a>
            </div>
          </div>
        </div>
        <div className="mt-8 border-t border-border-subtle pt-6 text-center">
          <p className="text-sm text-text-muted">&copy; {currentYear} Ledova contributors</p>
          <p className="text-xs text-text-body">Local development and public testnets only</p>
        </div>
      </div>
    </footer>
  );
}
