/**
 * The state round trip between the wizard and the assistant.
 *
 * The server is stateless: every turn the modal rebuilds the state from the
 * wizard, and everything the backend wrote must land back in the wizard.
 * Whatever this round trip does not carry is silently forgotten between
 * turns. The owner found the first casualty: a skipped question was not
 * carried, so "skip" was forgotten the moment the next answer was sent, and
 * the same optional question came back after every turn — swallowing the
 * answers meant for other questions.
 */
import { describe, expect, it } from "vitest";

import { AssistantState } from "../api/client";
import { DraftLine } from "../components/ReviewLinesPanel";
import { buildAssistantState, draftLinesFromAssistant, wizardDgEntriesFromAssistant, retainAssistantDgAnswers } from "./assistantState";

const args = (draftLines: DraftLine[], skipped: string[] = []) => ({
  modality: "road",
  draftLines,
  resultLines: undefined,
  dgEntries: [],
  docValues: {},
  selectedDocs: null,
  skippedQuestions: skipped,
});

function roundTrip(backendState: AssistantState, current: DraftLine[]) {
  const lines = draftLinesFromAssistant(backendState, current) ?? current;
  const skipped = (backendState.skipped_questions ?? []).map(String);
  return buildAssistantState(args(lines, skipped));
}

describe("the wizard/assistant state round trip", () => {
  it("carries a skipped question through to the next turn", () => {
    const backendState: AssistantState = {
      modality: "road",
      draft_lines: [{ id: 1, description: "stalen plaat", quantity: 1, unit: "pcs" }],
      skipped_questions: ["goods:1:goods_dimensions"],
    };
    const rebuilt = roundTrip(backendState, []);
    expect(rebuilt.skipped_questions).toEqual(["goods:1:goods_dimensions"]);
  });

  it("carries an answered measurement through to the next turn", () => {
    const backendState: AssistantState = {
      modality: "road",
      draft_lines: [{
        id: 1, description: "stalen plaat", quantity: 1, unit: "pcs",
        length_cm: 200, width_cm: 100, height_cm: 2,
      }],
    };
    const rebuilt = roundTrip(backendState, []);
    const line = rebuilt.draft_lines?.[0] as Record<string, unknown>;
    expect([line.length_cm, line.width_cm, line.height_cm]).toEqual([200, 100, 2]);
  });

  it("keeps what the wizard holds beyond the exchanged fields", () => {
    const current: DraftLine[] = [{
      id: 1, description: "stalen plaat", quantity: 1, unit: "pcs",
      wall_thickness_mm: 8,
    }];
    const lines = draftLinesFromAssistant(
      { draft_lines: [{ id: 1, description: "stalen plaat", quantity: 1, unit: "pcs" }] },
      current,
    );
    expect(lines?.[0].wall_thickness_mm).toBe(8);
  });

  it("a stated weight travels as the answer, a computed one never does", () => {
    const stated = buildAssistantState(args([{
      id: 1, description: "machineonderdeel", quantity: 4, unit: "pallet",
      weight_each_kg: 900,
    }]));
    expect((stated.draft_lines?.[0] as Record<string, unknown>).weight_each_kg).toBe(900);

    const computed = buildAssistantState({
      ...args([{ id: 1, description: "stalen plaat", quantity: 1, unit: "pcs" }]),
      resultLines: [{ line_id: 1, weight_each_kg: 314 } as never],
    });
    const line = computed.draft_lines?.[0] as Record<string, unknown>;
    expect(line.weight_each_kg).toBeUndefined();
    expect(line.computed_weight_each_kg).toBe(314);
  });
});

it("undoing the intake clears every added line, including the last one", () => {
  expect(draftLinesFromAssistant({ draft_lines: [] }, [{ id: 1, description: "diesel", quantity: 20, unit: "jerrycan" }])).toEqual([]);
});

it("an omitted count stays visibly empty until the user answers it", () => {
  const result = draftLinesFromAssistant({ draft_lines: [{ id: 1, description: "goods", quantity: 1, quantity_unconfirmed: true }] }, []);
  expect(result?.[0].quantity).toBe("");
  expect(roundTrip({ draft_lines: [{ id: 1, description: "goods", quantity: 1, quantity_unconfirmed: true }] }, []).draft_lines?.[0].quantity_unconfirmed).toBe(true);
});

it("the weight basis survives closing and reopening", () => {
  const result = roundTrip({ draft_lines: [{ id: 1, description: "goods", quantity: 4, weight_each_kg: 200, weight_basis: "total", stated_weight_kg: 800 }] }, []);
  expect(result.draft_lines?.[0]).toMatchObject({ weight_basis: "total", stated_weight_kg: 800, weight_each_kg: 200 });
});

it("preserves an explicit other-substance decision until a new answer replaces it", () => {
  const current: DraftLine[] = [{ id: 1, description: "goods", quantity: 2, unit: "pcs", dangerous_goods: true, dg_decision: "other" }];
  const built = buildAssistantState(args(current));
  expect(draftLinesFromAssistant(built, current)?.[0].dg_decision).toBe("other");
  built.draft_lines![0].dg_dismissed = true;
  expect(draftLinesFromAssistant(built, current)?.[0].dg_decision).toBe("rejected");
});


it("keeps DG answers attached after a draft row has been deleted", () => {
  const built = buildAssistantState({ ...args([{ id: 7, description: "diesel", quantity: 20, unit: "jerrycan" }]),
    dgEntries: [{ line_id: 1, vehicle: "diesel", products: [{ un_number: "1202", carriage_mode: "packages" }] }],
    resultLines: [{ line_id: 1, detected_un_numbers: ["1202"] } as never],
  });
  expect(built.dg_entries?.[0].line_id).toBe(7);
  expect(built.draft_lines?.[0].detected_un_numbers).toEqual(["1202"]);
  expect(wizardDgEntriesFromAssistant(built)[0].line_id).toBe(1);
});

it("moving from goods to DG keeps collected packaging answers only for the same substance", () => {
  const prepared = [{ line_id: 1, vehicle: "diesel", products: [{ un_number: "1202" }] }];
  const answered = [{ line_id: 1, vehicle: "diesel", products: [{ un_number: "1202", carriage_mode: "packages", type_of_package: "3A1" }] }];
  expect(retainAssistantDgAnswers(prepared, answered)[0].products[0].type_of_package).toBe("3A1");
  expect(retainAssistantDgAnswers([{ ...prepared[0], products: [{ un_number: "1203" }] }], answered)[0].products[0].type_of_package).toBeUndefined();
});
