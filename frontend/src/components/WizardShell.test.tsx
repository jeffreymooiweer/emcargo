/**
 * The frame around a shipment.
 *
 * What is worth asserting here is not that a header renders — it is the two
 * promises the shell makes that the four stacked strips before it could not:
 *
 * - **The action bar leaves nothing permanently underneath it.** It is
 *   `sticky bottom-0`, which keeps it in the layout and gives it its own
 *   height at the end of the page. A `fixed` bar is out of the layout: the
 *   last row of the form, and whatever error is standing next to it, stays
 *   covered at every scroll position. Measured on a phone viewport, the
 *   sticky bar does float over the page while you are scrolled above its
 *   resting place — that overlap is one scroll away, and the class is what it
 *   is because of the other one, which is not.
 * - **A step's buttons end up in it.** They are written where the step ends
 *   and rendered where the shell puts them, so no step has to know it is in a
 *   shell — and a step rendered on its own still shows its own buttons.
 *
 * And one thing the plan promised the owner in as many words: the transport
 * mode in this header is a *switcher*. The tiles at `/` are where a shipment
 * is begun and they are not moved out of the way for it, so the link to them
 * is here too, and this asserts it.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import WizardShell, { WizardActions } from "./WizardShell";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}:${Object.values(options).join(",")}` : key,
    i18n: { language: "nl" },
  }),
}));

const STEPS = [
  { n: 1, key: "lines" as const, label: "Goederen" },
  { n: 2, key: "details" as const, label: "Gegevens" },
  { n: 3, key: "export" as const, label: "Controleren" },
];

function shell(props: Partial<Parameters<typeof WizardShell>[0]> = {}) {
  return render(
    <MemoryRouter>
      <WizardShell
        title="Nieuwe zending"
        modality="road"
        modalities={["road", "rail", "sea"]}
        onModality={vi.fn()}
        steps={STEPS}
        currentStep={1}
        {...props}
      >
        {props.children ?? <p>de stap zelf</p>}
      </WizardShell>
    </MemoryRouter>,
  );
}

/** The bar the steps' buttons are put in. */
function bar(): HTMLElement | null {
  return document.querySelector("div.sticky");
}

describe("the frame around a shipment", () => {
  it("says which shipment this is", () => {
    shell();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Nieuwe zending");
  });

  it("says how far along you are, for a screen too narrow for the labels", () => {
    shell({ currentStep: 2 });
    expect(screen.getByText(/wizard.progressStep:2,3/)).toBeInTheDocument();
  });

  it("switches the mode of the shipment already being entered", async () => {
    const onModality = vi.fn();
    shell({ onModality });
    await userEvent.selectOptions(screen.getByLabelText("wizard.mode"), "rail");
    expect(onModality).toHaveBeenCalledWith("rail");
  });

  it("keeps a door to the tiles, which are not moved out of the way for it", () => {
    shell();
    expect(screen.getByRole("link", { name: "wizard.changeModality" })).toHaveAttribute(
      "href",
      "/?choose=1",
    );
  });

  it("puts a step's buttons in the bar at the foot", () => {
    shell({
      children: (
        <div>
          <p>de stap zelf</p>
          <WizardActions>
            <button type="button">Verder</button>
          </WizardActions>
        </div>
      ),
    });
    const foot = bar();
    expect(foot).not.toBeNull();
    expect(within(foot!).getByRole("button", { name: "Verder" })).toBeInTheDocument();
  });

  it("holds that bar in the layout rather than out of it", () => {
    // The difference between sticky and fixed is the promise: a sticky bar
    // takes its own height at the end of the page, so nothing ends up under
    // it at rest. A fixed one covers the last row at every scroll position.
    shell({
      children: (
        <WizardActions>
          <button type="button">Verder</button>
        </WizardActions>
      ),
    });
    expect(bar()!.className).toContain("bottom-0");
    expect(bar()!.className).not.toContain("fixed");
  });

  it("draws no bar for a step that has no buttons", () => {
    shell();
    expect(bar()).toBeNull();
  });

  it("counts what is waiting to be looked at, beside the way forward", () => {
    shell({
      attention: 2,
      children: (
        <WizardActions>
          <button type="button">Verder</button>
        </WizardActions>
      ),
    });
    expect(within(bar()!).getByText("wizard.attention:2")).toBeInTheDocument();
  });

  it("says nothing about attention when there is none", () => {
    shell({
      attention: 0,
      children: (
        <WizardActions>
          <button type="button">Verder</button>
        </WizardActions>
      ),
    });
    expect(screen.queryByText(/wizard.attention/)).toBeNull();
  });

  it("leaves a step's buttons where they are written when there is no shell", () => {
    // How a step stays testable on its own, and how it stays usable if it is
    // ever rendered somewhere other than the wizard.
    render(
      <WizardActions>
        <button type="button">Verder</button>
      </WizardActions>,
    );
    expect(screen.getByRole("button", { name: "Verder" })).toBeInTheDocument();
    expect(bar()).toBeNull();
  });
});
