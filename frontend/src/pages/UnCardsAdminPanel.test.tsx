/** The download action must agree with the publication state shown above it.
 * A known-empty feed used to leave an active download button that could only
 * produce the English error in the reported screenshot. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { api } from "../api/client";
import nl from "../i18n/nl.json";
import { UnCardsAdminPanel } from "./SettingsPage";

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), undoable: vi.fn() }));
vi.mock("../toast/ToastProvider", () => ({ useToast: () => toast }));

const language = createInstance();
const local = { installed: false, location: "/data/un-cards" };

beforeEach(async () => {
  vi.clearAllMocks();
  await language.init({ lng: "nl", resources: { nl: { translation: nl } }, interpolation: { escapeValue: false } });
  vi.spyOn(api, "unCardStoreStatus").mockResolvedValue({ local });
  vi.spyOn(api, "unCardStoreDownloadLatest").mockResolvedValue({ ok: true, imported: 1 });
});

afterEach(() => vi.restoreAllMocks());

function mount() {
  render(<I18nextProvider i18n={language}><UnCardsAdminPanel /></I18nextProvider>);
  return screen.findByText(nl.settings.unCardsNone);
}

const download = () => screen.getByRole("button", { name: nl.settings.unCardsDownload });
const check = () => screen.getByRole("button", { name: nl.settings.unCardsCheck });

describe("UN card publication state", () => {
  it("loads local status and lets the administrator directly request a download", async () => {
    await mount();
    expect(api.unCardStoreStatus).toHaveBeenCalledTimes(1);
    expect(api.unCardStoreStatus).toHaveBeenCalledWith(false);
    expect(download()).toBeEnabled();
    fireEvent.click(download());
    await waitFor(() => expect(api.unCardStoreDownloadLatest).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(nl.settings.unCardsImportDone));
  });

  it("disables downloading after confirming that no set exists", async () => {
    await mount();
    vi.mocked(api.unCardStoreStatus).mockResolvedValue({ local, remote: { available: false } });
    fireEvent.click(check());
    await screen.findByText(nl.settings.unCardsNoRelease);
    await waitFor(() => expect(check()).toBeEnabled());
    expect(download()).toBeDisabled();
    fireEvent.click(download());
    expect(api.unCardStoreDownloadLatest).not.toHaveBeenCalled();
  });

  it("enables downloading when a later check finds the newly published set", async () => {
    await mount();
    vi.mocked(api.unCardStoreStatus).mockResolvedValue({ local, remote: { available: false } });
    fireEvent.click(check());
    await waitFor(() => expect(download()).toBeDisabled());
    await waitFor(() => expect(check()).toBeEnabled());
    vi.mocked(api.unCardStoreStatus).mockResolvedValue({
      local, remote: { available: true, update_available: true, tag: "un-cards-2026.09.12-1" },
    });
    fireEvent.click(check());
    await waitFor(() => expect(download()).toBeEnabled());
    fireEvent.click(download());
    await waitFor(() => expect(api.unCardStoreDownloadLatest).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("allows retrying a network failure without claiming that the feed is empty", async () => {
    await mount();
    vi.mocked(api.unCardStoreStatus).mockResolvedValue({
      local, remote: { available: false, reachable: false, error: "offline" },
    });
    fireEvent.click(check());
    await screen.findByText(nl.settings.unCardsRemoteUnreachable);
    await waitFor(() => expect(download()).toBeEnabled());
    expect(screen.queryByText(nl.settings.unCardsNoRelease)).not.toBeInTheDocument();
  });

  it("shows the translated API message without an English Error prefix", async () => {
    await mount();
    vi.mocked(api.unCardStoreDownloadLatest).mockRejectedValue(new Error(nl.errors.un_cards.no_release));
    fireEvent.click(download());
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(nl.errors.un_cards.no_release));
    expect(toast.success).not.toHaveBeenCalled();
  });
});
