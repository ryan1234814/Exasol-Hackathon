// Light/dark switch. The dark palette is the :root default; the light palette is
// a variable override under :root[data-theme="light"], so no component needs to
// know which one is live.
//
// localStorage is only ever touched inside try/catch: in a private window (or
// with storage disabled) *reading* throws, and a theme toggle that crashes the
// demo is worse than one that forgets.
import { useCallback, useEffect, useState } from 'react'

const KEY = 'wardq.theme'
const DARK = 'dark'
const LIGHT = 'light'

function stored() {
  try {
    const value = window.localStorage.getItem(KEY)
    if (value === LIGHT || value === DARK) return value
  } catch {
    /* storage unavailable — fall through to the default */
  }
  return DARK
}

export function useTheme() {
  const [theme, setTheme] = useState(stored)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      window.localStorage.setItem(KEY, theme)
    } catch {
      /* still applied for this session via the data attribute */
    }
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((current) => (current === DARK ? LIGHT : DARK))
  }, [])

  return [theme, toggle]
}
