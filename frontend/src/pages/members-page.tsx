import { useCallback, useEffect, useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Users } from "lucide-react"

import { RequirePerm } from "@/components/require-perm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  ApiError,
  createMember,
  deleteMember,
  listMembers,
  listRoles,
  replaceMemberRoles,
  type Member,
  type Role,
} from "@/lib/api"
import { Perm } from "@/lib/permissions"
import { useSession } from "@/lib/session"

export function MembersPage() {
  return (
    <RequirePerm perm={Perm.MEMBER_READ}>
      <MembersBody />
    </RequirePerm>
  )
}

function MembersBody() {
  const { me, hasPerm, refresh } = useSession()
  const tenantId = me?.current_tenant?.id
  const canWrite = hasPerm(Perm.MEMBER_WRITE)
  const [members, setMembers] = useState<Member[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Member | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const memberPage = await listMembers()
      setMembers(memberPage.items)
      if (canWrite) {
        try {
          const rolePage = await listRoles()
          setRoles(rolePage.items)
        } catch {
          setRoles([])
        }
      } else {
        setRoles([])
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [canWrite])

  useEffect(() => {
    void load()
  }, [load, tenantId])

  return (
    <>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl tracking-tight">成员</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "加载中…" : `本租户 ${members.length} 人`}
          </p>
        </div>
        {canWrite ? (
          <Button onClick={() => setCreating(true)}>添加成员</Button>
        ) : null}
      </div>

      {members.length === 0 && !loading ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-16 text-center">
          <Users className="mb-3 size-8 text-muted-foreground" />
          <p className="text-sm font-medium">还没有成员</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>姓名</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
                {canWrite ? (
                  <TableHead className="w-28 text-right">操作</TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <TableRow key={member.id}>
                  <TableCell className="font-medium">
                    {member.user.display_name}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {member.user.email}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {member.roles.length === 0 ? (
                        <span className="text-sm text-muted-foreground">
                          未分配
                        </span>
                      ) : (
                        member.roles.map((role) => (
                          <Badge
                            key={role.id}
                            variant={role.is_system ? "secondary" : "outline"}
                          >
                            {role.name}
                          </Badge>
                        ))
                      )}
                    </div>
                  </TableCell>
                  {canWrite ? (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditing(member)}
                      >
                        修改角色
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CreateMemberDialog
        open={creating}
        roles={roles}
        onClose={() => setCreating(false)}
        onSaved={() => {
          setCreating(false)
          void load()
        }}
      />
      <EditMemberRolesDialog
        member={editing}
        roles={roles}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          void refresh()
          void load()
        }}
      />
    </>
  )
}

function RoleChecks({
  roles,
  selected,
  onToggle,
}: {
  roles: Role[]
  selected: string[]
  onToggle: (roleId: string, checked: boolean) => void
}) {
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      {roles.map((role) => (
        <label key={role.id} className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={selected.includes(role.id)}
            onCheckedChange={(value) => onToggle(role.id, value === true)}
          />
          <span>{role.name}</span>
          {role.is_system ? <Badge variant="secondary">系统</Badge> : null}
        </label>
      ))}
    </div>
  )
}

function CreateMemberDialog({
  open,
  roles,
  onClose,
  onSaved,
}: {
  open: boolean
  roles: Role[]
  onClose: () => void
  onSaved: () => void
}) {
  const [email, setEmail] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [roleIds, setRoleIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
      setEmail("")
      setDisplayName("")
      setRoleIds([])
    }
  }, [open])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextEmail = email.trim()
    const nextName = displayName.trim()
    if (!nextEmail || !nextName) {
      toast.error("请填写邮箱和姓名")
      return
    }
    setSubmitting(true)
    try {
      await createMember({
        email: nextEmail,
        display_name: nextName,
        role_ids: roleIds,
      })
      toast.success("已添加成员")
      onSaved()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "添加失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>添加成员</DialogTitle>
            <DialogDescription>
              按邮箱找到或创建用户，再赋给当前租户的角色。
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="member-email">邮箱</FieldLabel>
              <Input
                id="member-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="member-name">姓名</FieldLabel>
              <Input
                id="member-name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel>角色</FieldLabel>
              <RoleChecks
                roles={roles}
                selected={roleIds}
                onToggle={(roleId, checked) =>
                  setRoleIds((current) =>
                    checked
                      ? [...current, roleId]
                      : current.filter((id) => id !== roleId),
                  )
                }
              />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "添加中…" : "添加"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function EditMemberRolesDialog({
  member,
  roles,
  onClose,
  onSaved,
}: {
  member: Member | null
  roles: Role[]
  onClose: () => void
  onSaved: () => void
}) {
  const { me } = useSession()
  const [roleIds, setRoleIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (member) {
      setRoleIds(member.roles.map((role) => role.id))
    }
  }, [member])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!member) {
      return
    }
    setSubmitting(true)
    try {
      await replaceMemberRoles(member.id, roleIds)
      toast.success("已更新角色")
      onSaved()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "保存失败")
    } finally {
      setSubmitting(false)
    }
  }

  async function onRemove() {
    if (!member) {
      return
    }
    setSubmitting(true)
    try {
      await deleteMember(member.id)
      toast.success("已移出租户")
      onSaved()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "移除失败")
    } finally {
      setSubmitting(false)
    }
  }

  const isSelf = member?.user.id === me?.user.id

  return (
    <Dialog open={member !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>修改角色</DialogTitle>
            <DialogDescription>
              {member?.user.display_name} · {member?.user.email}
              。勾选后保存，立即替换该成员在当前租户的角色。
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel>角色</FieldLabel>
              <RoleChecks
                roles={roles}
                selected={roleIds}
                onToggle={(roleId, checked) =>
                  setRoleIds((current) =>
                    checked
                      ? [...current, roleId]
                      : current.filter((id) => id !== roleId),
                  )
                }
              />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="destructive"
              disabled={submitting}
              onClick={() => void onRemove()}
            >
              {isSelf ? "移出自己" : "移出租户"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "保存中…" : "保存"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
