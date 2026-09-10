import { createCameraWindowAccess } from './cameraWindowAccess';

it('fences a replacement owner against earlier callbacks and teardown', () => {
  const access = createCameraWindowAccess(true);
  access.attach('old');
  access.update('old', { ownerId: 'old', generation: 1, allowed: true });
  expect(access.getSnapshot().allowed).toBe(true);
  access.attach('new');
  expect(access.getSnapshot().allowed).toBe(false);
  access.update('old', { ownerId: 'old', generation: 100, allowed: true });
  expect(access.getSnapshot().allowed).toBe(false);
  access.update('new', { ownerId: 'new', generation: 1, allowed: true });
  access.detach('old');
  expect(access.getSnapshot().allowed).toBe(true);
  access.detach('new');
  expect(access.getSnapshot().allowed).toBe(false);
  access.update('new', { ownerId: 'new', generation: 2, allowed: true });
  expect(access.getSnapshot().allowed).toBe(false);
});

it.each([
  null,
  {},
  { generation: -1 },
  { generation: NaN },
  { generation: Infinity },
  { generation: 0.5 },
  { generation: 1, allowed: 'true' },
])('ignores malformed native data: %p', (input) => {
  const access = createCameraWindowAccess(true);
  access.attach('owner');
  access.update('owner', { ownerId: 'owner', allowed: true, ...input });
  expect(access.getSnapshot().allowed).toBe(false);
  access.update('owner', { ownerId: 'owner', generation: 1, allowed: true });
  expect(access.getSnapshot().allowed).toBe(true);
});
