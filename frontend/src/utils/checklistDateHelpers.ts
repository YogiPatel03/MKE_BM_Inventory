export function parseLocalDate(dateStr: string): Date | null {
  const parts = dateStr.split("-");
  if (parts.length !== 3) return null;
  const [year, month, day] = parts.map(Number);
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  const d = new Date(year, month - 1, day);
  if (d.getFullYear() !== year || d.getMonth() !== month - 1 || d.getDate() !== day) return null;
  return d;
}

export function formatSabhaDate(sabhaDate?: string | null, weekStart?: string | null): string {
  if (sabhaDate) {
    const d = parseLocalDate(sabhaDate);
    if (d) return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  }
  if (weekStart) {
    const d = parseLocalDate(weekStart);
    if (d) return `Week of ${d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`;
  }
  return "Sabha date unavailable";
}
