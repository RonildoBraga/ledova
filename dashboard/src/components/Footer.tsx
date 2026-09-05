import { useQuery } from '@tanstack/react-query';
import { getOperator, CACHE_TIMING } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useAuth } from '@hooks/useAuth';

const MARKETING_URL = import.meta.env.VITE_MARKETING_URL || '';

interface FooterProps {
  minimal?: boolean;
}

function useOperatorName(): string | null {
  const { isAuthenticated } = useAuth();
  const query = useQuery({
    queryKey: ['operator'],
    queryFn: () => getOperator(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });
  return query.data?.data?.name || null;
}

export default function Footer({ minimal = false }: FooterProps) {
  const currentYear = new Date().getFullYear();
  const operatorName = useOperatorName();

  if (minimal) {
    return (
      <footer className="relative mt-auto border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-6 text-center sm:px-6 lg:px-8">
          {operatorName && <p className="text-sm text-text-secondary">Operated by {operatorName}</p>}
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
            {operatorName && <p className="mt-2 text-sm text-text-body">Operated by {operatorName}</p>}
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
