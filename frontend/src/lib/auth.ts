type AccessTokenGetter = () => Promise<string | undefined>

let getAccessToken: AccessTokenGetter | undefined
let tenantId: string | undefined

export function configureApi(options: { getAccessToken: AccessTokenGetter }): void {
  getAccessToken = options.getAccessToken
}

export function setTenantId(next: string | undefined): void {
  tenantId = next
}

export async function currentAccessToken(): Promise<string | undefined> {
  return getAccessToken?.()
}

export function currentTenantId(): string | undefined {
  return tenantId
}
