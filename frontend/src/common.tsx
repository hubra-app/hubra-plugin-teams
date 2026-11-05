import { useState } from 'react'
import { useToast } from '@hubra/plugin-sdk'
import { errorText } from './api'

/** Runs an action with a busy flag and a toast for errors. */
export function useAction() {
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try {
      await fn()
      if (ok) notify('success', ok)
      return true
    } catch (err) {
      notify('error', errorText(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, run }
}

