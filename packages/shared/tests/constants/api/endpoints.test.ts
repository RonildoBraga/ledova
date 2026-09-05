import { PORTFOLIO_ENDPOINTS } from '../../../src/constants/api';

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
});
