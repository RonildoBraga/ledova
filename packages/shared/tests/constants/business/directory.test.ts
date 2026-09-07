import { DIRECTORY_COPY } from '../../../src/constants/business/directory';

const OPT_IN = /opted in|opts in/i;
const DEPLOYED = /deployed/i;

describe('the directory empty state', () => {
  it('names both halves of the condition it is explaining', () => {
    expect(DIRECTORY_COPY.EMPTY_BODY).toMatch(OPT_IN);
    expect(DIRECTORY_COPY.EMPTY_BODY).toMatch(DEPLOYED);
  });

  it('does not claim that no issuer has opted in', () => {
    expect(DIRECTORY_COPY.EMPTY_BODY).not.toMatch(/no issuer has/i);
  });

  it('leaves the market empty state naming only deployment, which is its only condition', () => {
    expect(DIRECTORY_COPY.MARKET_EMPTY_BODY).toMatch(DEPLOYED);
    expect(DIRECTORY_COPY.MARKET_EMPTY_BODY).not.toMatch(OPT_IN);
  });
});
