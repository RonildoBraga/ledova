module.exports = {
  preset: 'jest-expo',
  testMatch: ['<rootDir>/src/**/*.test.ts', '<rootDir>/src/**/*.test.tsx'],
  setupFiles: ['<rootDir>/jest.setup.js'],
  clearMocks: true,
  restoreMocks: true,
};
