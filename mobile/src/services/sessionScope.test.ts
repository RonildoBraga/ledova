import { getSessionEpoch, invalidateSessionScope, subscribeSession } from './sessionScope';

it('notifies only the listeners present at the start of an invalidation', () => {
  const replacement = jest.fn();
  let removeReplacement = () => {};
  const removeOriginal = subscribeSession(() => {
    removeOriginal();
    removeReplacement = subscribeSession(replacement);
  });
  const epoch = getSessionEpoch();
  try {
    invalidateSessionScope();
    expect(getSessionEpoch()).toBe(epoch + 1);
    expect(replacement).not.toHaveBeenCalled();
    invalidateSessionScope();
    expect(replacement).toHaveBeenCalledTimes(1);
  } finally {
    removeOriginal();
    removeReplacement();
  }
});

it('continues session retirement and other listeners after a subscriber throws', () => {
  const warning = jest.spyOn(console, 'warn').mockImplementation(() => {});
  const removeFailure = subscribeSession(() => {
    throw new Error('private subscriber diagnostic');
  });
  const completed = jest.fn();
  const removeControl = subscribeSession(completed);
  const epoch = getSessionEpoch();
  try {
    expect(() => invalidateSessionScope()).not.toThrow();
    expect(getSessionEpoch()).toBe(epoch + 1);
    expect(completed).toHaveBeenCalledTimes(1);
    expect(warning).toHaveBeenCalledWith('Session cleanup did not complete.');
    removeControl();
    invalidateSessionScope();
    expect(completed).toHaveBeenCalledTimes(1);
  } finally {
    removeFailure();
    removeControl();
  }
});
