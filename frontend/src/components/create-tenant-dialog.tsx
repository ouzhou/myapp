import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ApiError, createTenant } from "@/lib/api"

type CreateTenantDialogProps = {
  onCreated: () => void
}

export function CreateTenantDialog({ onCreated }: CreateTenantDialogProps) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [submitting, setSubmitting] = useState(false)

  function reset() {
    setName("")
    setSlug("")
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = name.trim()
    const trimmedSlug = slug.trim().toLowerCase()
    if (!trimmedName || !trimmedSlug) {
      toast.error("请填写名称和编码")
      return
    }

    setSubmitting(true)
    try {
      const tenant = await createTenant({
        name: trimmedName,
        slug: trimmedSlug,
      })
      toast.success(`已创建「${tenant.name}」`)
      reset()
      setOpen(false)
      onCreated()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "创建失败"
      toast.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
        }
        setOpen(next)
      }}
    >
      <DialogTrigger asChild>
        <Button>新建租户</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>新建租户</DialogTitle>
            <DialogDescription>
              会同时写入系统角色「租户管理员」。成员需要之后在该租户内添加。
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="tenant-name">名称</FieldLabel>
              <Input
                id="tenant-name"
                name="name"
                autoComplete="off"
                placeholder="例如：示例公司"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={255}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="tenant-slug">编码</FieldLabel>
              <Input
                id="tenant-slug"
                name="slug"
                autoComplete="off"
                placeholder="例如：acme"
                value={slug}
                onChange={(event) => setSlug(event.target.value)}
                maxLength={64}
                required
              />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "创建中…" : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
