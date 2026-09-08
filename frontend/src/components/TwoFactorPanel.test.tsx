import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import TwoFactorPanel from "./TwoFactorPanel";
import { api } from "../api/client";
import { ToastProvider } from "../toast/ToastProvider";
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../api/client", () => ({ api: {
  twoFactorStatus: vi.fn(), twoFactorNewRecoveryCodes: vi.fn(), twoFactorSendCode: vi.fn(),
} }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.twoFactorStatus).mockResolvedValue({ active: true, method: "email", required: true, recovery_codes_left: 8 });
  vi.mocked(api.twoFactorNewRecoveryCodes).mockResolvedValue({ recovery_codes: ["synthetic-recovery-code"] });
  vi.mocked(api.twoFactorSendCode).mockResolvedValue({ ok: true });
});
it("requires proof before replacing recovery codes even when two-factor verification is mandatory", async () => {
  render(<ToastProvider><TwoFactorPanel /></ToastProvider>);
  await userEvent.click(await screen.findByRole("button", { name: "twoFactor.newCodes" }));
  expect(api.twoFactorNewRecoveryCodes).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "twoFactor.confirm" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "twoFactor.sendCode" }));
  expect(api.twoFactorSendCode).toHaveBeenCalledOnce();
  await userEvent.type(screen.getByLabelText("twoFactor.renewCode"), "123456");
  await userEvent.click(screen.getByRole("button", { name: "twoFactor.confirm" }));
  await waitFor(() => expect(api.twoFactorNewRecoveryCodes).toHaveBeenCalledWith("123456"));
  expect(await screen.findByText("synthetic-recovery-code")).toBeInTheDocument();
  expect(screen.queryByLabelText("twoFactor.renewCode")).not.toBeInTheDocument();
});
