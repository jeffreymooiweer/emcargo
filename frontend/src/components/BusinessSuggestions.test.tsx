import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import BusinessSuggestions from "./BusinessSuggestions";
import { api } from "../api/client";
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../api/client", () => ({ api: { geoBusinesses: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

it("requires a choice and keeps distinct establishments selectable", async () => {
  const choices = [{ name: "PLUS", address: "Street 1\nWezep" }, { name: "PLUS", address: "Street 2\nWezep" }];
  vi.mocked(api.geoBusinesses).mockResolvedValue({ results: choices, available: true });
  const pick = vi.fn();
  render(<BusinessSuggestions name="PLUS" city="Wezep" language="nl" disabled={false} onPick={pick} />);
  await screen.findByText("assistant.business.choose");
  expect(pick).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /Street 2/ }));
  expect(pick).toHaveBeenCalledWith(choices[1]);
});

it("does not apply one result automatically or replace it with a stale lookup", async () => {
  let resolveOld!: (value: { results: { name: string; address: string }[]; available: boolean }) => void;
  vi.mocked(api.geoBusinesses).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValueOnce({ results: [{ name: "Bosch", address: "Street 3\nStuttgart" }], available: true });
  const pick = vi.fn();
  const { rerender } = render(<BusinessSuggestions name="PLUS" city="Wezep" language="nl" disabled={false} onPick={pick} />);
  rerender(<BusinessSuggestions name="Bosch" city="Stuttgart" language="nl" disabled={false} onPick={pick} />);
  await screen.findByText("assistant.business.confirm");
  resolveOld({ results: [{ name: "PLUS", address: "Old address" }], available: true });
  await waitFor(() => expect(screen.queryByText("Old address")).toBeNull());
  expect(pick).not.toHaveBeenCalled();
});

it("leaves manual entry available when the provider fails", async () => {
  vi.mocked(api.geoBusinesses).mockRejectedValue(new Error("offline"));
  render(<BusinessSuggestions name="PLUS" city="Wezep" language="nl" disabled={false} onPick={vi.fn()} />);
  await screen.findByText("assistant.business.unavailable");
  fireEvent.click(screen.getByRole("button", { name: "assistant.business.manual" }));
  expect(screen.queryByRole("region")).toBeNull();
});
