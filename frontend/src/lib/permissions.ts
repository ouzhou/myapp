export const Perm = {
  PROJECT_READ: "project:read",
  PROJECT_WRITE: "project:write",
  ROLE_READ: "role:read",
  ROLE_WRITE: "role:write",
  MEMBER_READ: "member:read",
  MEMBER_WRITE: "member:write",
} as const

export type PermCode = (typeof Perm)[keyof typeof Perm]

export const PERM_LABELS: Record<string, string> = {
  [Perm.PROJECT_READ]: "查看项目",
  [Perm.PROJECT_WRITE]: "编辑项目",
  [Perm.ROLE_READ]: "查看角色",
  [Perm.ROLE_WRITE]: "管理角色",
  [Perm.MEMBER_READ]: "查看成员",
  [Perm.MEMBER_WRITE]: "管理成员",
}

export function permLabel(code: string): string {
  return PERM_LABELS[code] ?? code
}
