import { AUTH_ENDPOINTS, PORTFOLIO_ENDPOINTS, USER_ACCOUNT_ENDPOINTS } from '../../src/api';

describe('API Endpoints', () => {
  describe('PORTFOLIO_ENDPOINTS', () => {
    it('should have portfolio endpoints defined', () => {
      expect(PORTFOLIO_ENDPOINTS).toBeDefined();
      expect(PORTFOLIO_ENDPOINTS.BASE).toBe('/api/portfolios/');
    });

    it('should have function endpoints that generate correct URLs', () => {
      const portfolioId = 'test-uuid-123';
      const detailUrl = PORTFOLIO_ENDPOINTS.DETAIL(portfolioId);

      expect(detailUrl).toBe(`/api/portfolios/${portfolioId}/`);
      expect(detailUrl).toContain(portfolioId);
    });
  });

  describe('USER_ACCOUNT_ENDPOINTS', () => {
    it('should have user account endpoints defined', () => {
      expect(USER_ACCOUNT_ENDPOINTS).toBeDefined();
      expect(USER_ACCOUNT_ENDPOINTS.BASE).toBe('/api/user-accounts/');
    });

    it('should generate correct detail URLs', () => {
      const accountId = 'account-456';
      const detailUrl = USER_ACCOUNT_ENDPOINTS.DETAIL(accountId);

      expect(detailUrl).toBe(`/api/user-accounts/${accountId}/`);
    });
  });

  describe('URL Structure', () => {
    it('should have correct base URL structure', () => {
      expect(PORTFOLIO_ENDPOINTS.BASE).toMatch(/^\/api\//);
      expect(USER_ACCOUNT_ENDPOINTS.BASE).toMatch(/^\/api\//);
    });
  });
});
