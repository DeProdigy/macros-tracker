/**
 * Guards on the three shared components.
 *
 * These assert the things a screen cannot see itself doing wrong. A button that
 * shrinks below the tap minimum still looks fine in a screenshot, and a screen
 * that ignores the notch looks fine on the one simulator someone checked.
 */

import { describe, expect, it, jest } from "@jest/globals";
import { fireEvent, screen } from "@testing-library/react-native";
import { Text } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Body, Display, Label } from "@/components/ui/text";
import { numeralScaleCap, tapTarget, type } from "@/lib/theme";
import { renderWithProviders } from "@/test-utils/render";

/**
 * Insets from an iPhone with a notch.
 *
 * `SafeAreaProvider` measures the real window at runtime and reports zeroes in
 * a test renderer, so the numbers have to be injected. These are an iPhone 15's.
 */
const INSETS = { top: 59, bottom: 34, left: 0, right: 0 };
const FRAME = { x: 0, y: 0, width: 393, height: 852 };

const renderInSafeArea = (ui: React.ReactElement) =>
  renderWithProviders(
    <SafeAreaProvider initialMetrics={{ insets: INSETS, frame: FRAME }}>{ui}</SafeAreaProvider>,
  );

/** Flatten a possibly nested style prop into one object. */
const styleOf = (element: { props: { style?: unknown } }): Record<string, unknown> => {
  const flatten = (value: unknown): Record<string, unknown> => {
    if (Array.isArray(value)) return Object.assign({}, ...value.map(flatten));
    return (value ?? {}) as Record<string, unknown>;
  };
  return flatten(element.props.style);
};

describe("Button", () => {
  it("reaches the tap-target minimum", () => {
    renderInSafeArea(<Button onPress={jest.fn()} title="Log food" />);

    expect(styleOf(screen.getByRole("button")).minHeight as number).toBeGreaterThanOrEqual(
      tapTarget,
    );
  });

  it("uppercases a primary label and leaves a secondary one alone", () => {
    renderInSafeArea(
      <>
        <Button onPress={jest.fn()} title="Log food" />
        <Button onPress={jest.fn()} title="Not now" variant="secondary" />
      </>,
    );

    expect(screen.getByText("LOG FOOD")).toBeTruthy();
    expect(screen.getByText("Not now")).toBeTruthy();
  });

  it("blocks presses and reports itself busy while working", () => {
    const onPress = jest.fn();
    renderInSafeArea(<Button busy onPress={onPress} title="Save" />);

    fireEvent.press(screen.getByRole("button"));

    expect(onPress).not.toHaveBeenCalled();
    expect(screen.getByRole("button").props.accessibilityState).toMatchObject({
      busy: true,
      disabled: true,
    });
  });

  it("blocks presses when disabled", () => {
    const onPress = jest.fn();
    renderInSafeArea(<Button disabled onPress={onPress} title="Save" />);

    fireEvent.press(screen.getByRole("button"));

    expect(onPress).not.toHaveBeenCalled();
  });
});

describe("Screen", () => {
  it("pads for the notch and the home indicator", () => {
    renderInSafeArea(
      <Screen testID="content">
        <Text>Today</Text>
      </Screen>,
    );

    const content = screen.getByTestId("content");
    expect(styleOf(content).paddingBottom).toBe(INSETS.bottom);
    expect(screen.getByText("Today")).toBeTruthy();
  });

  it("gives the bottom inset to a footer instead of the content", () => {
    renderInSafeArea(
      <Screen footer={<Button onPress={jest.fn()} title="Log food" />} testID="content">
        <Text>Today</Text>
      </Screen>,
    );

    // The content must not pad for the home indicator as well, or the gap above
    // the button doubles.
    expect(styleOf(screen.getByTestId("content")).paddingBottom).toBe(0);
  });

  it("skips an inset the caller opts out of", () => {
    renderInSafeArea(
      <Screen edges={["bottom"]} testID="content">
        <Text>Camera</Text>
      </Screen>,
    );

    expect(styleOf(screen.getByTestId("content")).paddingBottom).toBe(INSETS.bottom);
  });
});

describe("text roles", () => {
  it("caps Dynamic Type on a numeral", () => {
    renderInSafeArea(<Display>660</Display>);

    expect(screen.getByText("660").props.maxFontSizeMultiplier).toBe(numeralScaleCap);
  });

  it("leaves Dynamic Type uncapped on a sentence", () => {
    renderInSafeArea(<Body>Point the camera at your food.</Body>);

    expect(
      screen.getByText("Point the camera at your food.").props.maxFontSizeMultiplier,
    ).toBeUndefined();
  });

  it("uses the mono family for a label", () => {
    renderInSafeArea(<Label>PROTEIN</Label>);

    expect(styleOf(screen.getByText("PROTEIN")).fontFamily).toBe(type.label.fontFamily);
  });
});
