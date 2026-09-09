import { currentAccessToken, currentTenantId } from "@/lib/auth"

export type Envelope<T> = {
  code: number
  message: string
  data: T
}

export type PageResult<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type Project = {
  id: string
  tenant_id: string
  name: string
  description: string | null
  status: string | null
  created_at: string
  updated_at: string
}

export type ProjectCreate = {
  name: string
  description?: string | null
  status?: string | null
}

export type TenantSummary = {
  id: string
  slug: string
  name: string
  status: string
}

export type Tenant = TenantSummary & {
  created_at: string
  updated_at: string
}

export type UserProfile = {
  id: string
  email: string
  display_name: string
  status: string
  is_platform_admin: boolean
}

export type Me = {
  user: UserProfile
  tenants: TenantSummary[]
  current_tenant: TenantSummary | null
  permissions: string[]
}

export type Permission = {
  code: string
}

export type Role = {
  id: string
  tenant_id: string
  code: string
  name: string
  is_system: boolean
  permissions: string[]
  created_at: string
  updated_at: string
}

export type RoleSummary = {
  id: string
  code: string
  name: string
  is_system: boolean
}

export type RoleCreate = {
  code: string
  name: string
  permissions: string[]
}

export type Member = {
  id: string
  tenant_id: string
  user: UserProfile
  roles: RoleSummary[]
  status: string
  created_at: string
  updated_at: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: number

  constructor(status: number, code: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
  }
}

async function authHeaders(init?: HeadersInit): Promise<Headers> {
  const headers = new Headers(init)
  const token = await currentAccessToken()
  if (!token) {
    throw new ApiError(401, 40100, "未登录")
  }
  headers.set("Authorization", `Bearer ${token}`)
  const tenant = currentTenantId()
  if (tenant) {
    headers.set("X-Tenant-Id", tenant)
  }
  return headers
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders(init?.headers)
  if (init?.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  let response: Response
  try {
    response = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError(0, 0, "无法连接后端，请确认 FastAPI 已在 :8000 运行")
  }

  if (response.status === 204) {
    return undefined as T
  }

  let payload: Envelope<T> | { code?: number; message?: string }
  try {
    payload = (await response.json()) as Envelope<T>
  } catch {
    throw new ApiError(response.status, 0, `请求失败（HTTP ${response.status}）`)
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload.code ?? 0,
      payload.message ?? `请求失败（HTTP ${response.status}）`,
    )
  }

  return (payload as Envelope<T>).data
}

export function listProjects(): Promise<PageResult<Project>> {
  return request("/api/v1/projects/?page=1&page_size=50")
}

export function createProject(payload: ProjectCreate): Promise<Project> {
  return request("/api/v1/projects/", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function getMe(): Promise<Me> {
  return request("/api/v1/me")
}

export function listTenants(): Promise<PageResult<Tenant>> {
  return request("/api/v1/tenants?page=1&page_size=50")
}

export function createTenant(payload: {
  slug: string
  name: string
}): Promise<Tenant> {
  return request("/api/v1/tenants", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateTenantStatus(
  tenantId: string,
  status: "active" | "disabled",
): Promise<Tenant> {
  return request(`/api/v1/tenants/${tenantId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  })
}

export function switchCurrentTenant(tenantId: string): Promise<Me> {
  return request("/api/v1/me/current-tenant", {
    method: "PUT",
    body: JSON.stringify({ tenant_id: tenantId }),
  })
}

export function listPermissionCatalog(): Promise<Permission[]> {
  return request("/api/v1/permissions")
}

export function listRoles(): Promise<PageResult<Role>> {
  return request("/api/v1/roles?page=1&page_size=50")
}

export function createRole(payload: RoleCreate): Promise<Role> {
  return request("/api/v1/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateRole(
  roleId: string,
  payload: { code?: string; name?: string },
): Promise<Role> {
  return request(`/api/v1/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export function deleteRole(roleId: string): Promise<void> {
  return request(`/api/v1/roles/${roleId}`, { method: "DELETE" })
}

export function replaceRolePermissions(
  roleId: string,
  permissions: string[],
): Promise<Role> {
  return request(`/api/v1/roles/${roleId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ permissions }),
  })
}

export function listMembers(): Promise<PageResult<Member>> {
  return request("/api/v1/members?page=1&page_size=50")
}

export function createMember(payload: {
  email: string
  display_name: string
  role_ids: string[]
}): Promise<Member> {
  return request("/api/v1/members", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function deleteMember(membershipId: string): Promise<void> {
  return request(`/api/v1/members/${membershipId}`, { method: "DELETE" })
}

export function replaceMemberRoles(
  membershipId: string,
  roleIds: string[],
): Promise<Member> {
  return request(`/api/v1/members/${membershipId}/roles`, {
    method: "PUT",
    body: JSON.stringify({ role_ids: roleIds }),
  })
}
