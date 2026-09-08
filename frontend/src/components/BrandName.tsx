/** Product lettering is shared by the shell and the sign-in screen. */
export default function BrandName({ name }: { name?: string }) {
  return !name || name === "EMCargo" ? <><span className="emcargo-initials">EM</span>Cargo</> : <>{name}</>;
}
