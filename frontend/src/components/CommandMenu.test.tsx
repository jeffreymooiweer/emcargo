import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import CommandMenu from "./CommandMenu";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
beforeEach(() => {
  // jsdom does not implement native modal focus or Escape. Those are checked
  // in the browser; here we verify the application's keyboard/navigation logic.
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
it("opens from the keyboard, filters the permitted destinations and navigates with Enter", async () => {
  render(<MemoryRouter><CommandMenu destinations={[{ to: "/", label: "Nieuwe zending" }, { to: "/trips", label: "Ritten" }]} /><Routes><Route path="/trips" element={<p>Trip page</p>} /></Routes></MemoryRouter>);
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  const input = screen.getByRole("textbox", { name: "studio.quickFind" });
  expect(input).toHaveFocus();
  expect(screen.queryByRole("button", { name: /Beheer/ })).not.toBeInTheDocument();
  await userEvent.type(input, "ritten");
  expect(screen.queryByRole("button", { name: /Nieuwe zending/ })).not.toBeInTheDocument();
  await userEvent.keyboard("{Enter}");
  expect(screen.getByText("Trip page")).toBeInTheDocument();
  expect(document.querySelector("dialog")).not.toHaveAttribute("open");
});
it("moves up to the last result from the search field and restores the trigger on close", async () => {
  render(<MemoryRouter><CommandMenu destinations={[{ to: "/", label: "First" }, { to: "/trips", label: "Last" }]} /></MemoryRouter>);
  const trigger = screen.getByRole("button", { name: /studio.quickFind/ });
  await userEvent.click(trigger);
  await userEvent.keyboard("{ArrowUp}");
  expect(screen.getByRole("button", { name: /Last/ })).toHaveFocus();
  await userEvent.click(screen.getByRole("button", { name: "nav.closeMenu" }));
  expect(trigger).toHaveFocus();
});
