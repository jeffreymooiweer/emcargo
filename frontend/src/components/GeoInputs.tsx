import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, GeoAddress, GeoLocation, GeoLocationType } from "../api/client";

const inputClass =
  "w-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg px-3 py-2 text-sm min-h-[40px]";

const TYPE_ICONS: Record<GeoLocationType, string> = { airport: "✈", port: "⚓", station: "🚆" };

/** Fields from the shared "locations" block get location autocomplete —
 *  the same set wherever a location is asked, wizard and assistant alike. */
export const LOCATION_FIELD_KEYS = new Set([
  "place_of_receipt",
  "loading_point",
  "discharge_point",
  "place_of_delivery",
  "final_destination",
]);

/** Which location types are suggested per transport mode. */
export const MODALITY_LOCATION_TYPES: Record<string, GeoLocationType[]> = {
  air: ["airport"],
  sea: ["port"],
  inland: ["port"],
  rail: ["station"],
  road: ["airport", "port", "station"],
  multimodal: ["airport", "port", "station"],
};

interface PickItem {
  label: string;
  sublabel?: string;
  icon?: string;
  value: string;
}

export function formatLocation(loc: GeoLocation): string {
  const region = loc.city && loc.city !== loc.name ? `${loc.city}, ${loc.country}` : loc.country;
  return `${loc.name} (${loc.code}), ${region}`;
}

export function formatAddress(addr: GeoAddress): string {
  const street = [addr.street, addr.housenumber].filter(Boolean).join(" ");
  const cityLine = [addr.postcode, addr.city].filter(Boolean).join(" ");
  const lines = [addr.name && addr.name !== addr.street ? addr.name : "", street, cityLine, addr.country];
  return lines.filter(Boolean).join("\n");
}

function locationItem(loc: GeoLocation): PickItem {
  return {
    label: `${loc.name} (${loc.code})`,
    sublabel: [loc.city, loc.subdivision, loc.country].filter(Boolean).join(", "),
    icon: TYPE_ICONS[loc.type],
    value: formatLocation(loc),
  };
}

function usePickItems(fetcher: (q: string) => Promise<PickItem[]>, query: string, enabled: boolean) {
  const [items, setItems] = useState<PickItem[]>([]);
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef(0);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!enabled || query.trim().length < 2) {
      setItems([]);
      return;
    }
    const id = ++latest.current;
    timer.current = window.setTimeout(() => {
      fetcher(query)
        .then((results) => {
          if (latest.current === id) setItems(results);
        })
        .catch(() => {
          if (latest.current === id) setItems([]);
        });
    }, 250);
    return () => window.clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, enabled]);

  return { items, clear: () => setItems([]) };
}

function Dropdown({ items, onPick }: { items: PickItem[]; onPick: (item: PickItem) => void }) {
  if (items.length === 0) return null;
  return (
    <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      {items.map((item, i) => (
        <li key={i}>
          <button
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              onPick(item);
            }}
            className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm text-slate-800 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {item.icon && <span className="mt-0.5 shrink-0">{item.icon}</span>}
            <span className="min-w-0">
              <span className="block truncate">{item.label}</span>
              {item.sublabel && (
                <span className="block truncate text-xs text-slate-500 dark:text-slate-400">{item.sublabel}</span>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function LocationInput({
  value,
  onChange,
  types,
  includeAddresses,
  className,
  id,
}: {
  value: string;
  onChange: (value: string) => void;
  types: GeoLocationType[];
  includeAddresses?: boolean;
  className?: string;
  /** So a label can point at the field and a caller can focus it. */
  id?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(false);

  const fetcher = async (q: string): Promise<PickItem[]> => {
    const [locations, addresses] = await Promise.all([
      api.geoLocations(q, types).then((r) => r.results.map(locationItem)),
      includeAddresses && q.trim().length >= 3
        ? api
            .geoAddress(q, "en", 4)
            .then((r) => r.results.map((a): PickItem => ({ label: a.label, icon: "📍", value: a.label })))
            .catch(() => [])
        : Promise.resolve([] as PickItem[]),
    ]);
    return [...locations, ...addresses];
  };

  const { items, clear } = usePickItems(fetcher, value, open && !picked);

  return (
    <div className="relative">
      <input
        id={id}
        className={className ?? inputClass}
        value={value}
        placeholder={t("geo.locationPlaceholder")}
        onChange={(e) => {
          setPicked(false);
          onChange(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          setOpen(false);
          clear();
        }}
        autoComplete="off"
      />
      {open && !picked && (
        <Dropdown
          items={items}
          onPick={(item) => {
            onChange(item.value);
            setPicked(true);
            clear();
          }}
        />
      )}
    </div>
  );
}

export function AddressTextarea({
  value,
  onChange,
  textareaClassName,
  textareaId,
  rows,
}: {
  value: string;
  onChange: (value: string) => void;
  textareaClassName: string;
  /** The address itself, not the lookup box above it: that is the field the
   *  export needs, so that is what a label points at and a caller focuses. */
  textareaId?: string;
  rows?: number;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const { items, clear } = usePickItems(
    (q) =>
      api
        .geoAddress(q, "en")
        .then((r) => r.results.map((a): PickItem => ({ label: a.label, icon: "📍", value: formatAddress(a) }))),
    query,
    open,
  );

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <input
          className={inputClass}
          value={query}
          placeholder={t("geo.addressPlaceholder")}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            setOpen(false);
            clear();
          }}
          autoComplete="off"
        />
        {open && (
          <Dropdown
            items={items}
            onPick={(item) => {
              onChange(item.value);
              setQuery("");
              clear();
            }}
          />
        )}
      </div>
      <textarea id={textareaId} rows={rows} className={textareaClassName} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
