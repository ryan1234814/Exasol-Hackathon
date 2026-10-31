import React from 'react'
import { createRoot } from 'react-dom/client'
import './chartSetup'
import './styles.css'
import App from './App'

// Register the offline cache once, and only in a production build.
//
// This sits outside React on purpose: React 18 StrictMode invokes effects twice
// in development, so registering from a component would fire two
// `navigator.serviceWorker.register` calls. The module-level flag covers the
// other double case — a hot reload re-executing this file — cheaply.
//
// Registration is fire-and-forget: a browser that refuses the worker (private
// window, no HTTPS on a LAN address, an old build) must still get the app.
let registered = false
if (import.meta.env.PROD && !registered) {
  registered = true
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {})
    })
  }
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
