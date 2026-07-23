import { describe, expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import LoginScreen from "../app/(auth)/login";

// Smoke test: proves Jest + React Native Testing Library render a screen.
// RSpec equivalent: a request/feature spec asserting the page renders.
describe("LoginScreen", () => {
  it("renders the placeholder copy", () => {
    const { getByText } = render(<LoginScreen />);
    expect(getByText(/placeholder for the auth epic/i)).toBeTruthy();
  });
});
