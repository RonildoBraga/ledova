import { createCameraAccess } from './cameraAccess';

it('starts blocked and gives each admission transition a fresh callback identity', () => {
  const access = createCameraAccess();
  expect(access.getSnapshot().allowed).toBe(false);
  access.setAllowed(true);
  const original = access.getSnapshot();
  expect(original.allowed).toBe(true);
  access.setAllowed(false);
  expect(access.getSnapshot().allowed).toBe(false);
  access.setAllowed(true);
  expect(access.getSnapshot().allowed).toBe(true);
  expect(access.getSnapshot()).not.toBe(original);
});

it('notifies only the subscriptions present when the transition begins', () => {
  const access = createCameraAccess();
  const replacement = jest.fn();
  const existing = jest.fn();
  const unsubscribe = access.subscribe(() => {
    unsubscribe();
    access.subscribe(replacement);
  });
  access.subscribe(existing);
  access.setAllowed(true);
  expect(replacement).not.toHaveBeenCalled();
  expect(existing).toHaveBeenCalledTimes(1);
  access.setAllowed(false);
  expect(replacement).toHaveBeenCalledTimes(1);
  expect(existing).toHaveBeenCalledTimes(2);
});

it('publishes retirement and notifies other cameras even if a subscriber throws', () => {
  const access = createCameraAccess();
  access.setAllowed(true);
  const warning = jest.spyOn(console, 'warn').mockImplementation(() => {});
  access.subscribe(() => {
    throw new Error('synthetic subscriber failure');
  });
  const remaining = jest.fn(() => expect(access.getSnapshot().allowed).toBe(false));
  access.subscribe(remaining);
  expect(() => access.setAllowed(false)).not.toThrow();
  expect(remaining).toHaveBeenCalledTimes(1);
  expect(warning.mock.calls).toEqual([['Camera pause notification did not complete.']]);
});
