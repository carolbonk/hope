import type { NteeCode } from "./types";

/** NTEE major groups (A-Z), shown when the search box is empty. */
export const NTEE_GROUPS: readonly NteeCode[] = (
  [
    ["A", "Arts, Culture and Humanities"],
    ["B", "Education"],
    ["C", "Environment"],
    ["D", "Animal-Related"],
    ["E", "Health Care"],
    ["F", "Mental Health and Crisis Intervention"],
    ["G", "Diseases, Disorders and Medical Disciplines"],
    ["H", "Medical Research"],
    ["I", "Crime and Legal-Related"],
    ["J", "Employment"],
    ["K", "Food, Agriculture and Nutrition"],
    ["L", "Housing and Shelter"],
    ["M", "Public Safety, Disaster Preparedness and Relief"],
    ["N", "Recreation and Sports"],
    ["O", "Youth Development"],
    ["P", "Human Services"],
    ["Q", "International, Foreign Affairs and National Security"],
    ["R", "Civil Rights, Social Action and Advocacy"],
    ["S", "Community Improvement and Capacity Building"],
    ["T", "Philanthropy, Voluntarism and Grantmaking Foundations"],
    ["U", "Science and Technology"],
    ["V", "Social Science"],
    ["W", "Public and Societal Benefit"],
    ["X", "Religion-Related"],
    ["Y", "Mutual and Membership Benefit"],
    ["Z", "Unknown"],
  ] as const
).map(([code, label]) => ({ code, label, group: code, group_label: label }));

const groupLabel = (code: string) => NTEE_GROUPS.find((g) => g.code === code[0])?.label ?? "";

export const NTEE_CODES: readonly NteeCode[] = (
  [
    ["B20", "Elementary and Secondary Schools"],
    ["B28", "Special Education"],
    ["B60", "Adult Education"],
    ["B90", "Educational Services"],
    ["B92", "Remedial Reading and Encouragement"],
    ["E20", "Hospitals"],
    ["E21", "Community Health Systems"],
    ["E30", "Ambulatory Health Center"],
    ["E32", "Community Clinics"],
    ["E40", "Reproductive Health Care"],
    ["E42", "Family Planning"],
    ["E50", "Rehabilitative Care"],
    ["E60", "Health Support"],
    ["E61", "Blood Banks"],
    ["E62", "Emergency Medical Services and Transport"],
    ["E65", "Organ and Tissue Banks"],
    ["E70", "Public Health"],
    ["E80", "Health (General and Financing)"],
    ["E86", "Patient Services - Entertainment, Recreation"],
    ["E90", "Nursing"],
    ["E91", "Nursing Facilities"],
    ["E92", "Home Health Care"],
    ["F20", "Substance Abuse Dependency, Prevention and Treatment"],
    ["F30", "Mental Health Treatment"],
    ["F32", "Community Mental Health Centers"],
    ["F40", "Hot Lines and Crisis Intervention"],
    ["F42", "Rape Victim Services"],
    ["F60", "Counseling"],
    ["F70", "Psychiatric Disorders"],
    ["K30", "Food Programs"],
    ["K31", "Food Banks and Pantries"],
    ["L20", "Housing Development, Construction and Management"],
    ["L41", "Homeless Shelters"],
    ["O20", "Youth Centers and Clubs"],
    ["O50", "Youth Development Programs"],
    ["P20", "Human Service Organizations"],
    ["P30", "Children and Youth Services"],
    ["P40", "Family Services"],
    ["P70", "Residential Care and Adult Day Programs"],
    ["P81", "Senior Centers"],
    ["P84", "Ethnic and Immigrant Centers"],
    ["W70", "Leadership Development"],
  ] as const
).map(([code, label]) => ({ code, label, group: code.charAt(0), group_label: groupLabel(code) }));

/** Search ranking: exact code, code prefix, label word prefix, then label substring. */
export function searchNteeCodes(q: string, limit = 20): NteeCode[] {
  const query = q.trim().toLowerCase();
  if (!query) return [...NTEE_GROUPS];
  const rank = (c: NteeCode): number => {
    const code = c.code.toLowerCase();
    const label = c.label.toLowerCase();
    if (code === query) return 0;
    if (code.startsWith(query)) return 1;
    if (label.split(/[\s,-]+/).some((w) => w.startsWith(query))) return 2;
    if (label.includes(query) || c.group_label.toLowerCase().includes(query)) return 3;
    return 9;
  };
  return NTEE_CODES.map((c) => [rank(c), c] as const)
    .filter(([r]) => r < 9)
    .sort((a, b) => a[0] - b[0] || a[1].code.localeCompare(b[1].code))
    .slice(0, limit)
    .map(([, c]) => c);
}

export const nteeLabel = (code: string): string => NTEE_CODES.find((c) => c.code === code)?.label ?? code;
