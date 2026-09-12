import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { expect, it } from "vitest";
import GroupagePage from "./GroupagePage";
import { LegacyTripRoute } from "./TripsPage";

function Destination() { const location = useLocation(); return <p>{location.pathname + location.search}</p>; }

it.each([
  ["/groupage", "/trips"],
  ["/groupage?trip=3", "/trips?trip=3"],
  ["/groupage?shipments=7,8", "/trips?shipments=7%2C8"],
  ["/trips/3", "/trips?trip=3"],
])("keeps the existing bookmark %s usable", async (source, target) => {
  render(<MemoryRouter initialEntries={[source]}><Routes>
    <Route path="/groupage" element={<GroupagePage />} />
    <Route path="/trips/:id" element={<LegacyTripRoute />} />
    <Route path="/trips" element={<Destination />} />
  </Routes></MemoryRouter>);
  expect(await screen.findByText(target)).toBeInTheDocument();
});
