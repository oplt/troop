import { apiFetch } from "./client";

export type Company = {
    id: string;
    owner_id: string;
    name: string;
    slug: string;
    brief_markdown: string;
    settings_json: Record<string, unknown>;
    created_at: string;
    updated_at: string;
};

export type CompanyCreatePayload = {
    name: string;
    slug: string;
    brief_markdown?: string;
    settings_json?: Record<string, unknown>;
};

export type CompanyUpdatePayload = {
    name?: string;
    brief_markdown?: string;
    settings_json?: Record<string, unknown>;
};

export async function listCompanies(): Promise<Company[]> {
    return apiFetch("/companies");
}

export async function createCompany(payload: CompanyCreatePayload): Promise<Company> {
    return apiFetch("/companies", { method: "POST", body: JSON.stringify(payload) });
}

export async function getDefaultCompany(): Promise<Company> {
    return apiFetch("/companies/default");
}

export async function updateCompany(
    companyId: string,
    payload: CompanyUpdatePayload,
): Promise<Company> {
    return apiFetch(`/companies/${companyId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}
