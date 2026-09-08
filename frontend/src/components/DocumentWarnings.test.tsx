/**
 * The warnings the exporter computes must reach the person about to download.
 *
 * `validate_document` on the backend returns (errors, warnings). The errors
 * always worked — export refuses with a 422 and the wizard shows them. The
 * warnings were computed and then went nowhere, along two routes at once: the
 * export route discarded them (`errors, _warnings = ...`), and the endpoint
 * that does return them, POST /documents/validate, had no caller in this
 * codebase at all. Fourteen `warnings.append` sites fed a dead channel — the
 * missing-unit notice of v1.61.1, the missing English shipping name, the lost
 * 1.1.3.6 exemption, the mixed-loading findings, the 8.6.3 tunnel message, and
 * the VGM mass check among them.
 *
 * What is pinned here is the shape of the fix: warnings appear on the document
 * card *before* the download, they never block it, and a validation endpoint
 * that fails leaves the card alone — a broken check must not take the export
 * step down with it.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentExportPayload } from "../api/client";

const validateDocument = vi.fn();
vi.mock("../api/client", () => ({
  api: { validateDocument: (payload: unknown) => validateDocument(payload) },
}));

import DocumentWarnings, { groupDocumentWarnings, useDocumentValidation } from "./DocumentWarnings";

function payload(key: string, quantity = "100"): DocumentExportPayload {
  return {
    document_key: key,
    values: { consignor_name: "Verzender BV" },
    lines: [],
    dangerous_goods: [{ line_id: "1", products: [{ un_number: "1090", adr_total_quantity: quantity }] }],
    output_language: "nl",
  } as unknown as DocumentExportPayload;
}

function Harness({ payloads, active }: { payloads: DocumentExportPayload[]; active: boolean }) {
  const warnings = useDocumentValidation(payloads, active, "Controle niet beschikbaar");
  return (
    <div>
      {payloads.map((p) => (
        <div key={p.document_key} data-testid={p.document_key}>
          <DocumentWarnings heading="Aandachtspunten" warnings={warnings[p.document_key] ?? []} />
        </div>
      ))}
    </div>
  );
}

beforeEach(() => {
  validateDocument.mockReset();
});

describe("de documentwaarschuwingen op de exportstap", () => {
  it("toont wat het validate-endpoint teruggeeft, per document", async () => {
    validateDocument.mockImplementation((p: DocumentExportPayload) =>
      Promise.resolve({
        document_key: p.document_key,
        errors: [],
        warnings: p.document_key === "cmr"
          ? ["ADR 5.4.1.1.1 (f): bij UN 1090 staat een totale hoeveelheid zonder eenheid."]
          : [],
      }),
    );
    render(<Harness payloads={[payload("cmr"), payload("packing_list")]} active={true} />);
    await waitFor(() =>
      expect(screen.getByText(/5\.4\.1\.1\.1 \(f\)/)).toBeInTheDocument(),
    );
    // The warning belongs to the CMR card and must not leak onto the other.
    expect(screen.getByTestId("cmr").textContent).toContain("5.4.1.1.1");
    expect(screen.getByTestId("packing_list").textContent).not.toContain("5.4.1.1.1");
  });

  it("rendert niets als er geen waarschuwingen zijn", async () => {
    validateDocument.mockResolvedValue({ document_key: "cmr", errors: [], warnings: [] });
    render(<Harness payloads={[payload("cmr")]} active={true} />);
    await waitFor(() => expect(validateDocument).toHaveBeenCalled());
    expect(screen.queryByText("Aandachtspunten")).not.toBeInTheDocument();
  });

  it("keeps a failed check visible on the affected document", async () => {
    // An empty list must never imply a successful check when its request failed.
    validateDocument.mockRejectedValue(new Error("boom"));
    render(<Harness payloads={[payload("cmr")]} active={true} />);
    await waitFor(() => expect(screen.getByText("Controle niet beschikbaar")).toBeInTheDocument());
  });

  it("vraagt niets zolang de exportstap niet open is", async () => {
    render(<Harness payloads={[payload("cmr")]} active={false} />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(validateDocument).not.toHaveBeenCalled();
  });

  it("valideert opnieuw wanneer de invoer verandert", async () => {
    validateDocument.mockResolvedValue({ document_key: "cmr", errors: [], warnings: [] });
    const { rerender } = render(<Harness payloads={[payload("cmr", "100")]} active={true} />);
    await waitFor(() => expect(validateDocument).toHaveBeenCalledTimes(1));
    rerender(<Harness payloads={[payload("cmr", "100 L")]} active={true} />);
    await waitFor(() => expect(validateDocument).toHaveBeenCalledTimes(2));
    // The same payload again is not a change; identity churn per render must
    // not become a request per render.
    rerender(<Harness payloads={[payload("cmr", "100 L")]} active={true} />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(validateDocument).toHaveBeenCalledTimes(2);
  });

  it("toont meerdere waarschuwingen als lijst", async () => {
    validateDocument.mockResolvedValue({
      document_key: "cmr", errors: [],
      warnings: ["Eerste waarschuwing", "Tweede waarschuwing"],
    });
    render(<Harness payloads={[payload("cmr")]} active={true} />);
    await waitFor(() => expect(screen.getByText("Tweede waarschuwing")).toBeInTheDocument());
    expect(screen.getByText("Eerste waarschuwing")).toBeInTheDocument();
    expect(screen.getByText("Aandachtspunten")).toBeInTheDocument();
  });
});


it("groups repeated warnings without dropping any affected document", () => {
  expect(groupDocumentWarnings({cmr: ["Missing unit", "Missing unit"], adr: ["Missing unit", "Tunnel E"], labels: []})).toEqual([
    {message: "Missing unit", documents: ["cmr", "adr"]},
    {message: "Tunnel E", documents: ["adr"]},
  ]);
});

it("clears stale findings as soon as the input changes", async () => {
  validateDocument.mockResolvedValueOnce({errors: [], warnings: ["Old substance warning"]});
  const {rerender} = render(<Harness payloads={[payload("cmr", "100")]} active />);
  await waitFor(() => expect(screen.getByText("Old substance warning")).toBeInTheDocument());
  validateDocument.mockImplementation(() => new Promise(() => {}));
  rerender(<Harness payloads={[payload("cmr", "200")]} active />);
  expect(screen.queryByText("Old substance warning")).not.toBeInTheDocument();
});
