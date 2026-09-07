// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuth } from '@hooks';
import { RootRedirect } from './RootRedirect';

vi.mock('@hooks', () => ({ useAuth: vi.fn() }));

const useAuthMock = vi.mocked(useAuth);
const THE_APPLICATION = 'http://localhost:5174/';

function renderRoot() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/signin" element={<p>Sign in</p>} />
        <Route path="/home" element={<p>Home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('where the front door sends a visitor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { href: THE_APPLICATION },
    });
  });

  afterEach(cleanup);

  it('sends a signed-out visitor to sign in, like every other guarded route', () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false } as ReturnType<typeof useAuth>);

    renderRoot();

    expect(screen.getByText('Sign in')).toBeTruthy();
  });

  it('does not leave the application, which is what stranded the visitor', () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false } as ReturnType<typeof useAuth>);

    renderRoot();

    expect(window.location.href).toBe(THE_APPLICATION);
  });

  it('sends a signed-in visitor to their home', () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false } as ReturnType<typeof useAuth>);

    renderRoot();

    expect(screen.getByText('Home')).toBeTruthy();
  });

  it('decides nothing while it does not yet know', () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: true } as ReturnType<typeof useAuth>);

    renderRoot();

    expect(screen.queryByText('Sign in')).toBeNull();
    expect(screen.queryByText('Home')).toBeNull();
    expect(window.location.href).toBe(THE_APPLICATION);
  });
});
