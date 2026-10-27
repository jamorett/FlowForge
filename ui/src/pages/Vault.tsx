// Locked milestones + access log. Max 3 evaluations, each with reason.
export function Vault() {
  return (
    <section aria-label="Vault" className="space-y-3">
      <h2 className="text-xl font-semibold">Vault</h2>
      <p className="text-sm">Locked flows stay greyed until a milestone: square_duct, nasa_wall_mounted_hump.</p>
      <p className="text-xs">At most 3 locked evaluations; every access is logged with a reason.</p>
    </section>
  );
}
