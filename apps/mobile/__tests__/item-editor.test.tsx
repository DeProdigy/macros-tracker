import { expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { ItemEditor } from "../components/item-editor";
import type { EditableFoodItem } from "../lib/entry-items";

const item: EditableFoodItem = {
  clientId: "test-item",
  name: "Chicken",
  portion_label: "1 piece",
  quantity: "1.00",
  calories: "190.00",
  protein_g: "20.00",
  fiber_g: "0.00",
};

const cases: [string, keyof EditableFoodItem, string][] = [
  ["Item 1 food name", "name", "Chicken thigh"],
  ["Item 1 portion", "portion_label", "2 pieces"],
  ["Item 1 quantity", "quantity", "2.00"],
  ["Item 1 calories", "calories", "200.00"],
  ["Item 1 protein", "protein_g", "22.00"],
  ["Item 1 fiber", "fiber_g", "1.00"],
];

it.each(cases)("reports changes from %s", (label, field, value) => {
  const onChange = jest.fn<(value: EditableFoodItem) => void>();
  render(<ItemEditor label="Item 1" value={item} onChange={onChange} />);

  fireEvent.changeText(screen.getByLabelText(label), value);

  expect(onChange).toHaveBeenCalledWith({ ...item, [field]: value });
});
