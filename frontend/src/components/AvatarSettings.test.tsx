import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import AvatarSettings from "./AvatarSettings";
import { ToastProvider } from "../toast/ToastProvider";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const api = vi.hoisted(() => ({ uploadMyAvatar: vi.fn(), deleteMyAvatar: vi.fn() }));
vi.mock("../api/client", () => ({ api }));
const profile = { id: 2, username: "Ada", email: "ada@example.com", role: "user", active: true, avatar_url: "/api/users/2/avatar?v=old" };
beforeEach(() => vi.clearAllMocks());

it("updates the shared account only after a successful upload and removal", async () => {
  const updated = { ...profile, avatar_url: "/api/users/2/avatar?v=new" };
  api.uploadMyAvatar.mockResolvedValue(updated);
  api.deleteMyAvatar.mockResolvedValue({ ...profile, avatar_url: null });
  const onUserChange = vi.fn();
  const { container } = render(<ToastProvider><AvatarSettings user={profile} onUserChange={onUserChange} /></ToastProvider>);
  const file = new File(["image"], "portrait.png", { type: "image/png" });
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file] } });
  await waitFor(() => expect(onUserChange).toHaveBeenCalledWith(updated));
  expect(container.querySelector("img")).toHaveAttribute("src", updated.avatar_url);
  await userEvent.click(screen.getByRole("button", { name: "profile.remove" }));
  await waitFor(() => expect(container.querySelector("img")).toBeNull());
  expect(onUserChange).toHaveBeenLastCalledWith({ ...profile, avatar_url: null });
});

it("keeps the existing avatar when the upload is refused", async () => {
  api.uploadMyAvatar.mockRejectedValue(new Error("invalid photo"));
  const onUserChange = vi.fn();
  const { container } = render(<ToastProvider><AvatarSettings user={profile} onUserChange={onUserChange} /></ToastProvider>);
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(["bad"], "portrait.png", { type: "image/png" })] } });
  expect(await screen.findByText(/invalid photo/)).toBeInTheDocument();
  expect(container.querySelector("img")).toHaveAttribute("src", profile.avatar_url);
  expect(onUserChange).not.toHaveBeenCalled();
});
