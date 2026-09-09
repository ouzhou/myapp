import { useCallback, useEffect, useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Lock, Shield } from "lucide-react"

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
  createRole,
  deleteRole,
  listPermissionCatalog,
  listRoles,
  replaceRolePermissions,
  updateRole,
  type Permission,
  type Role,
} from "@/lib/api"
import { Perm, permLabel } from "@/lib/permissions"
import { useSession } from "@/lib/session"

export function RolesPage() {
  return (
    <RequirePerm perm={Perm.ROLE_READ}>
      <RolesBody />
    </RequirePerm>
  )
}

function RolesBody() {
  const { me, hasPerm } = useSession()
  const tenantId = me?.current_tenant?.id
  const canWrite = hasPerm(Perm.ROLE_WRITE)
  const [roles, setRoles] = useState<Role[]>([])
  const [catalog, setCatalog] = useState<Permission[]>([])
  const [loading, setLoading] = useState(false)
  const [editor, setEditor] = useState<Role | "new" | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rolePage, perms] = await Promise.all([
        listRoles(),
        listPermissionCatalog(),
      ])
      setRoles(rolePage.items)
      setCatalog(perms)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, tenantId])

  return (
    <>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl tracking-tight">角色</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {loading ? "加载中…" : `本租户 ${roles.length} 个角色`}
          </p>
        </div>
        {canWrite ? (
          <Button onClick={() => setEditor("new")}>新建角色</Button>
        ) : null}
      </div>

      {roles.length === 0 && !loading ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-16 text-center">
          <Shield className="mb-3 size-8 text-muted-foreground" />
          <p className="text-sm font-medium">还没有角色</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>编码</TableHead>
                <TableHead>权限</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {roles.map((role) => (
                <TableRow key={role.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{role.name}</span>
                      {role.is_system ? (
                        <Badge variant="secondary">
                          <Lock className="size-3" />
                          系统
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{role.code}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {role.is_system
                      ? "全部权限"
                      : `${role.permissions.length} 项`}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditor(role)}
                    >
                      {role.is_system || !canWrite ? "查看" : "编辑"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <RoleEditor
        editor={editor}
        catalog={catalog}
        canWrite={canWrite}
        onClose={() => setEditor(null)}
        onSaved={() => {
          setEditor(null)
          void load()
        }}
      />
    </>
  )
}

function RoleEditor({
  editor,
  catalog,
  canWrite,
  onClose,
  onSaved,
}: {
  editor: Role | "new" | null
  catalog: Permission[]
  canWrite: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const isNew = editor === "new"
  const role = editor && editor !== "new" ? editor : null
  const locked = Boolean(role?.is_system)
  const editable = canWrite && !locked
  const [code, setCode] = useState("")
  const [name, setName] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!editor) {
      return
    }
    if (editor === "new") {
      setCode("")
      setName("")
      setSelected([])
      return
    }
    setCode(editor.code)
    setName(editor.name)
    setSelected(editor.permissions)
  }, [editor])

  function toggle(perm: string, checked: boolean) {
    setSelected((current) =>
      checked ? [...current, perm] : current.filter((item) => item !== perm),
    )
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editable) {
      return
    }
    const nextCode = code.trim()
    const nextName = name.trim()
    if (!nextCode || !nextName) {
      toast.error("请填写编码和名称")
      return
    }
    setSubmitting(true)
    try {
      if (isNew) {
        await createRole({
          code: nextCode,
          name: nextName,
          permissions: selected,
        })
        toast.success("已创建角色")
      } else if (role) {
        await updateRole(role.id, { code: nextCode, name: nextName })
        await replaceRolePermissions(role.id, selected)
        toast.success("已保存角色")
      }
      onSaved()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "保存失败")
    } finally {
      setSubmitting(false)
    }
  }

  async function onDelete() {
    if (!role || locked) {
      return
    }
    setSubmitting(true)
    try {
      await deleteRole(role.id)
      toast.success("已删除角色")
      onSaved()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "删除失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={editor !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isNew ? "新建角色" : locked ? "系统角色" : "编辑角色"}
            </DialogTitle>
            <DialogDescription>
              {locked
                ? "系统角色不可修改，权限始终是当前全部权限点。"
                : "编码在租户内唯一。权限改完下一个请求生效。"}
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="role-name">名称</FieldLabel>
              <Input
                id="role-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={!editable}
                maxLength={255}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="role-code">编码</FieldLabel>
              <Input
                id="role-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                disabled={!editable}
                maxLength={64}
                required
              />
            </Field>
            <Field>
              <FieldLabel>权限</FieldLabel>
              <div className="grid gap-2 rounded-lg border p-3">
                {catalog.map((item) => (
                  <label
                    key={item.code}
                    className="flex items-center gap-2 text-sm"
                  >
                    <Checkbox
                      checked={selected.includes(item.code)}
                      disabled={!editable}
                      onCheckedChange={(value) =>
                        toggle(item.code, value === true)
                      }
                    />
                    <span>{permLabel(item.code)}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {item.code}
                    </span>
                  </label>
                ))}
              </div>
            </Field>
          </FieldGroup>
          <DialogFooter>
            {editable && role ? (
              <Button
                type="button"
                variant="destructive"
                disabled={submitting}
                onClick={() => void onDelete()}
              >
                删除
              </Button>
            ) : null}
            <Button type="button" variant="outline" onClick={onClose}>
              {editable ? "取消" : "关闭"}
            </Button>
            {editable ? (
              <Button type="submit" disabled={submitting}>
                {submitting ? "保存中…" : "保存"}
              </Button>
            ) : null}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
