module.exports = {
  preset: 'jest-expo',
  testMatch: ['<rootDir>/src/**/*.test.ts', '<rootDir>/src/**/*.test.tsx'],
  setupFiles: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    '^react$': '<rootDir>/node_modules/react',
    '^react/(.*)$': '<rootDir>/node_modules/react/$1',
    '^@tanstack/react-query$': '<rootDir>/node_modules/@tanstack/react-query',
  },
  clearMocks: true,
  restoreMocks: true,
};
