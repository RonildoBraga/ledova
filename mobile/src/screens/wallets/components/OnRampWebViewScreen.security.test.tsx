import { render } from '@testing-library/react-native';
import WebView from 'react-native-webview';
import { OnRampWebViewScreen } from './OnRampWebViewScreen';
import { CameraAccessContext, createCameraAccess } from '../../../contexts/cameraAccess';
import { getSessionEpoch } from '../../../services/sessionScope';
import { AppState } from 'react-native';

let mockUrl = '';
let mockSessionEpoch = 0;
jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { url: mockUrl, sessionEpoch: mockSessionEpoch } }),
  useIsFocused: () => true,
  useNavigation: () => ({
    canGoBack: jest.fn(),
    goBack: jest.fn(),
    isFocused: () => true,
    addListener: () => () => {},
  }),
}));
jest.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: jest.fn() }) }));
jest.mock('../../../contexts', () => ({ useAppTheme: () => ({}), useThemedStyles: () => ({}) }));
jest.mock('../../../components/GradientBackground', () => ({
  GradientBackground: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('react-native-webview', () => jest.fn(() => null));

function screen() {
  const access = createCameraAccess();
  access.setAllowed(true);
  AppState.currentState = 'active';
  mockSessionEpoch = getSessionEpoch();
  return (
    <CameraAccessContext.Provider value={access}>
      <OnRampWebViewScreen />
    </CameraAccessContext.Provider>
  );
}

it('allows a secure provider and refuses a later insecure navigation', async () => {
  mockUrl = 'https://provider.example.test/form';
  await render(screen());
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
  await render(screen());
  expect(WebView).not.toHaveBeenCalled();
});
