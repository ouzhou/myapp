import { useHandleSignInCallback } from "@logto/react"
import { useNavigate } from "react-router-dom"

export function CallbackPage() {
  const navigate = useNavigate()
  const { isLoading, error } = useHandleSignInCallback(() => {
    navigate("/", { replace: true })
  })

  if (error) {
    return (
      <main className="flex min-h-svh items-center justify-center p-8">
        <p className="text-sm text-destructive">登录失败：{error.message}</p>
      </main>
    )
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-8">
      <p className="text-sm text-muted-foreground">
        {isLoading ? "正在完成登录…" : "即将跳转"}
      </p>
    </main>
  )
}
