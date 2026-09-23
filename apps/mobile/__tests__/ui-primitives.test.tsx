/**
 * Guards on the three shared components.
 *
 * These assert the things a screen cannot see itself doing wrong. A button that
 * shrinks below the tap minimum still looks fine in a screenshot, and a screen
 * that ignores the notch looks fine on the one simulator someone checked.
 */

import { describe, expect, it, jest } from "@jest/globals";
import { fireEvent, screen, within } from "@testing-library/react-native";
import { Keyboard, Text, TextInput } from "react-native";

import { Button } from "@/components/ui/button";
import { KEYBOARD_DONE_ID } from "@/components/ui/keyboard-done-bar";
import { Screen } from "@/components/ui/screen";
import { Body, Display, Label } from "@/components/ui/text";
import { numeralScaleCap, tapTarget, type } from "@/lib/theme";
import { TEST_INSETS } from "@/test-utils/insets";
import { renderWithProviders } from "@/test-utils/render";

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
    renderWithProviders(<Button onPress={jest.fn()} title="Log food" />);

    expect(styleOf(screen.getByRole("button")).minHeight as number).toBeGreaterThanOrEqual(
      tapTarget,
    );
  });

  it("uppercases every variant's visible label", () => {
    renderWithProviders(
      <>
        <Button onPress={jest.fn()} title="Log food" />
        <Button onPress={jest.fn()} title="Not now" variant="secondary" />
        <Button onPress={jest.fn()} title="Delete entry" variant="destructive" />
      </>,
    );

    expect(screen.getByText("LOG FOOD")).toBeTruthy();
    expect(screen.getByText("NOT NOW")).toBeTruthy();
    expect(screen.getByText("DELETE ENTRY")).toBeTruthy();
  });

  it("blocks presses and reports itself busy while working", () => {
    const onPress = jest.fn();
    renderWithProviders(<Button busy onPress={onPress} title="Save" />);

    fireEvent.press(screen.getByRole("button"));

    expect(onPress).not.toHaveBeenCalled();
    expect(screen.getByRole("button").props.accessibilityState).toMatchObject({
      busy: true,
      disabled: true,
    });
  });

  it("keeps a spoken label while busy, when the visible one is a spinner", () => {
    renderWithProviders(<Button busy onPress={jest.fn()} title="Save" />);

    expect(screen.getByRole("button").props.accessibilityLabel).toBe("Save");
  });

  it("speaks the label in its original case, not the uppercased one", () => {
    renderWithProviders(<Button onPress={jest.fn()} title="Log food" />);

    // The design uppercases a primary label. Some voices read an all-caps
    // string letter by letter, so the spoken label keeps the original.
    expect(screen.getByRole("button").props.accessibilityLabel).toBe("Log food");
    expect(screen.getByText("LOG FOOD")).toBeTruthy();
  });

  it("lets a caller override the spoken label", () => {
    renderWithProviders(
      <Button accessibilityLabel="Add food to 14 September" onPress={jest.fn()} title="Log food" />,
    );

    expect(screen.getByRole("button").props.accessibilityLabel).toBe("Add food to 14 September");
  });

  it("blocks presses when disabled", () => {
    const onPress = jest.fn();
    renderWithProviders(<Button disabled onPress={onPress} title="Save" />);

    fireEvent.press(screen.getByRole("button"));

    expect(onPress).not.toHaveBeenCalled();
  });
});

describe("Screen", () => {
  it("pads for the notch and the home indicator", () => {
    renderWithProviders(
      <Screen testID="content">
        <Text>Today</Text>
      </Screen>,
    );

    const content = screen.getByTestId("content");
    expect(styleOf(content).paddingBottom).toBe(TEST_INSETS.bottom);
    expect(screen.getByText("Today")).toBeTruthy();
  });

  it("gives the bottom inset to a footer instead of the content", () => {
    renderWithProviders(
      <Screen footer={<Button onPress={jest.fn()} title="Log food" />} testID="content">
        <Text>Today</Text>
      </Screen>,
    );

    // The content must not pad for the home indicator as well, or the gap above
    // the button doubles.
    expect(styleOf(screen.getByTestId("content")).paddingBottom).toBe(0);
  });

  it("skips an inset the caller opts out of", () => {
    renderWithProviders(
      <Screen edges={["bottom"]} testID="content">
        <Text>Camera</Text>
      </Screen>,
    );

    expect(styleOf(screen.getByTestId("content")).paddingBottom).toBe(TEST_INSETS.bottom);
  });

  it("closes the keyboard on a tap in empty space", () => {
    const dismiss = jest.spyOn(Keyboard, "dismiss");
    renderWithProviders(
      <Screen keyboard testID="content">
        <TextInput accessibilityLabel="Age in years" />
      </Screen>,
    );

    fireEvent.press(screen.getByTestId("content"));

    expect(dismiss).toHaveBeenCalled();
    dismiss.mockRestore();
  });

  it("lifts the footer with the content when the keyboard opens", () => {
    renderWithProviders(
      <Screen footer={<Button onPress={jest.fn()} title="Next" />} keyboard>
        <Text>How old are you?</Text>
      </Screen>,
    );

    // A footer outside the keyboard-avoiding view stays under the keyboard.
    // That hid Next on every onboarding question (MAC-77).
    const avoider = screen.getByTestId("screen-keyboard-avoider");
    expect(within(avoider).getByText("NEXT")).toBeTruthy();
  });

  it("offers a Done button for keyboards with no Return key", () => {
    const dismiss = jest.spyOn(Keyboard, "dismiss");
    renderWithProviders(
      <Screen keyboard>
        <TextInput inputAccessoryViewID={KEYBOARD_DONE_ID} keyboardType="number-pad" />
      </Screen>,
    );

    fireEvent.press(screen.getByLabelText("Close keyboard"));

    expect(dismiss).toHaveBeenCalled();
    dismiss.mockRestore();
  });

  it("adds no Done button to a screen without text input", () => {
    renderWithProviders(
      <Screen>
        <Text>Today</Text>
      </Screen>,
    );

    expect(screen.queryByLabelText("Close keyboard")).toBeNull();
  });
});

describe("text roles", () => {
  it("caps Dynamic Type on a numeral", () => {
    renderWithProviders(<Display>660</Display>);

    expect(screen.getByText("660").props.maxFontSizeMultiplier).toBe(numeralScaleCap);
  });

  it("leaves Dynamic Type uncapped on a sentence", () => {
    renderWithProviders(<Body>Point the camera at your food.</Body>);

    expect(
      screen.getByText("Point the camera at your food.").props.maxFontSizeMultiplier,
    ).toBeUndefined();
  });

  it("uses the mono family for a label", () => {
    renderWithProviders(<Label>PROTEIN</Label>);

    expect(styleOf(screen.getByText("PROTEIN")).fontFamily).toBe(type.label.fontFamily);
  });
});
