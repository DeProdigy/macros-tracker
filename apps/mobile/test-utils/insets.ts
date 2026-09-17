/**
 * The device insets every test renders against.
 *
 * An iPhone 15. Shared by `jest.setup.tsx`, which supplies them to any test
 * that renders a screen without a provider, and by `test-utils/render.tsx`,
 * which mirrors the real root layout.
 *
 * Non-zero on purpose. `react-native-safe-area-context` ships its own Jest mock
 * and it reports zeroes, which would let a screen that mishandles the notch
 * pass every test. Zero insets are the one device configuration this app will
 * never run on.
 *
 * Its own file so the setup module can read the numbers without importing the
 * render helper, which would drag React Native Testing Library into setup.
 */
export const TEST_INSETS = { top: 59, bottom: 34, left: 0, right: 0 };

export const TEST_FRAME = { x: 0, y: 0, width: 393, height: 852 };
