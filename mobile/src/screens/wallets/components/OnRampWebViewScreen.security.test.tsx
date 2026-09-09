import { render } from '@testing-library/react-native';
import WebView from 'react-native-webview';
import { OnRampWebViewScreen } from './OnRampWebViewScreen';

let mockUrl = '';
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { url: mockUrl } }),
  useNavigation: () => ({ canGoBack: jest.fn(), goBack: jest.fn() }),
}));
jest.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: jest.fn() }) }));
jest.mock('../../../contexts', () => ({ useAppTheme: () => ({}), useThemedStyles: () => ({}) }));
jest.mock('../../../components/GradientBackground', () => ({
  GradientBackground: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('react-native-webview', () => jest.fn(() => null));

it('allows a secure provider and refuses a later insecure navigation', async () => {
  mockUrl = 'https://provider.example.test/form';
  await render(<OnRampWebViewScreen />);
  const props = jest.mocked(WebView).mock.calls[0][0];
  expect(props.source).toEqual({ uri: mockUrl });
  expect(props.mixedContentMode).toBe('never');
  const navigate = props.onShouldStartLoadWithRequest;
  expect(navigate?.({ url: 'https://provider.example.test/next' } as Parameters<NonNullable<typeof navigate>>[0])).toBe(
    true,
  );
  expect(navigate?.({ url: 'http://provider.example.test/next' } as Parameters<NonNullable<typeof navigate>>[0])).toBe(
    false,
  );
});

it('does not create a WebView for an insecure initial provider URL', async () => {
  mockUrl = 'http://provider.example.test/form';
  await render(<OnRampWebViewScreen />);
  expect(WebView).not.toHaveBeenCalled();
});
